import { useState, useRef, useCallback, useEffect } from "react";
import { ChatMessage } from "@/types/chat";
import { A2AClient } from "@/a2a/client";
import { TaskSendParams, Message, Part, Artifact, MessageSendParams, MessageSendConfiguration } from "@/a2a/schema";
import { v4 as uuidv4 } from "uuid";
import {AgentCard, Task, TaskQueryParams, TextPart} from "@/a2a/schema";

interface UseChatProps {
    agentUrl?: string;
    isStreamingEnabled?: boolean;
    contextId?: string;
    getAccessToken?: () => Promise<string>;
}

export const useChat = ({ agentUrl, isStreamingEnabled = true, contextId, getAccessToken }: UseChatProps = {}) => {
    const [messages, setMessages] = useState<ChatMessage[]>([
        {
            id: 1,
            sender: "agent",
            content: "Hello, I am your AI Agent. How can I assist you today?",
            senderName: "Assistant",
            timestamp: new Date(),
        }
    ]);

    const [isLoading, setIsLoading] = useState<boolean>(false);
    const messagesEndRef = useRef<HTMLDivElement>(null);

    // Refs для управления анимацией печатания
    const typingTimeoutRef = useRef<NodeJS.Timeout | null>(null);
    const typingStateRef = useRef<{
        messageId: number | null;
        fullText: string;
        currentIndex: number;
        isTyping: boolean;
    }>({
        messageId: null,
        fullText: "",
        currentIndex: 0,
        isTyping: false
    });

    const scrollToBottom = useCallback(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, []);

    // Функция для симуляции печатания токенов
    const simulateTyping = useCallback((messageId: number, fullText: string, speed: number = 30) => {
        // Очищаем предыдущую анимацию
        if (typingTimeoutRef.current) {
            clearTimeout(typingTimeoutRef.current);
        }

        typingStateRef.current = {
            messageId,
            fullText,
            currentIndex: 0,
            isTyping: true
        };

        const typeNextChar = () => {
            const state = typingStateRef.current;

            if (state.currentIndex < state.fullText.length && state.isTyping) {
                // Определяем следующий токен (слово или символ)
                let nextIndex = state.currentIndex + 1;

                // Ускоряем печатание для пробелов и знаков препинания
                const currentChar = state.fullText[state.currentIndex];
                if (currentChar === ' ' || /[.,!?;:]/.test(currentChar)) {
                    speed = 10;
                } else if (/[a-zA-Zа-яА-ЯёЁ0-9]/.test(currentChar)) {
                    // Для обычных символов пытаемся найти конец слова
                    while (nextIndex < state.fullText.length &&
                           /[a-zA-Zа-яА-ЯёЁ0-9]/.test(state.fullText[nextIndex])) {
                        nextIndex++;
                    }
                    speed = Math.random() * 40 + 20; // 20-60ms для слов
                } else {
                    speed = 50; // Медленнее для специальных символов
                }

                const displayText = state.fullText.substring(0, nextIndex);

                setMessages(prev =>
                    prev.map(msg =>
                        msg.id === messageId
                            ? { ...msg, content: displayText + "▋" } // Добавляем курсор
                            : msg
                    )
                );

                typingStateRef.current.currentIndex = nextIndex;

                typingTimeoutRef.current = setTimeout(typeNextChar, speed);
            } else {
                // Завершаем печатание
                setMessages(prev =>
                    prev.map(msg =>
                        msg.id === messageId
                            ? { ...msg, content: state.fullText } // Убираем курсор
                            : msg
                    )
                );

                typingStateRef.current.isTyping = false;
            }
        };

        typeNextChar();
    }, []);

    // Функция для остановки анимации печатания
    const stopTyping = useCallback(() => {
        if (typingTimeoutRef.current) {
            clearTimeout(typingTimeoutRef.current);
            typingTimeoutRef.current = null;
        }

        const state = typingStateRef.current;
        if (state.isTyping && state.messageId) {
            setMessages(prev =>
                prev.map(msg =>
                    msg.id === state.messageId
                        ? { ...msg, content: state.fullText }
                        : msg
                )
            );
            typingStateRef.current.isTyping = false;
        }
    }, []);

    // Очистка таймеров при размонтировании
    useEffect(() => {
        return () => {
            if (typingTimeoutRef.current) {
                clearTimeout(typingTimeoutRef.current);
            }
        };
    }, []);

    // Функция для преобразования ChatMessage в A2A Message формат
    const convertChatMessageToA2AMessage = useCallback((chatMessage: ChatMessage): Message => {
        const parts: Part[] = [
            {
                kind: "text",
                text: chatMessage.content,
                metadata: undefined
            }
        ];

        return {
            messageId: `chat-${chatMessage.id}-${Date.now()}`,
            role: chatMessage.sender === "user" ? "user" : "agent",
            parts: parts,
            kind: "message",
            ...(contextId && { contextId: contextId }), // Условно добавляем contextId
            metadata: {
                timestamp: chatMessage.timestamp.toISOString(),
                senderName: chatMessage.senderName,
                originalId: chatMessage.id
            }
        };
    }, [contextId]);

    // Функция для получения истории последних 10 сообщений в формате A2A
    const getMessageHistory = useCallback((currentMessages: ChatMessage[]): Message[] => {
        // Берем последние 10 сообщений (исключая приветственное сообщение если это единственное)
        const messagesToInclude = currentMessages.length === 1 && currentMessages[0].id === 1
            ? [] // Не включаем начальное приветственное сообщение
            : currentMessages.slice(-10); // Берем последние 10 сообщений

        return messagesToInclude.map(convertChatMessageToA2AMessage);
    }, [convertChatMessageToA2AMessage]);

    // Обычная отправка сообщения (новая схема)
    const sendMessageSync = useCallback(async (content: string) => {
        const client = new A2AClient(agentUrl!, window.fetch.bind(window), getAccessToken);
        const messageId = uuidv4();

        // Получаем историю сообщений
        const messageHistory = getMessageHistory(messages);

        // Создаем конфигурацию
        const configuration: MessageSendConfiguration = {
            acceptedOutputModes: ["text"],
            historyLength: messageHistory.length,
            blocking: true
        };

        // Создаем message объект с условным включением contextId
        const message: Message = {
            messageId: messageId,
            role: "user",
            parts: [{ text: content, kind: "text" }],
            kind: "message",
            ...(contextId && { contextId: contextId })
        };

        const sendParams: MessageSendParams = {
            message: message,
            configuration,
            metadata: {
                history: messageHistory
            }
        };

        const response = await client.sendMessage(sendParams);
        return response;
    }, [agentUrl, messages, getMessageHistory, contextId, getAccessToken]);

    // Новая версия с поддержкой Parts
    const sendMessageSyncWithParts = useCallback(async (parts: Part[]) => {
        const client = new A2AClient(agentUrl!, window.fetch.bind(window), getAccessToken);
        const messageId = uuidv4();

        // Получаем историю сообщений
        const messageHistory = getMessageHistory(messages);

        // Создаем конфигурацию
        const configuration: MessageSendConfiguration = {
            acceptedOutputModes: ["text"],
            historyLength: messageHistory.length,
            blocking: true
        };

        // Создаем message объект с условным включением contextId
        const message: Message = {
            messageId: messageId,
            role: "user",
            parts: parts,
            kind: "message",
            ...(contextId && { contextId: contextId })
        };

        const sendParams: MessageSendParams = {
            message: message,
            configuration,
            metadata: {
                history: messageHistory
            }
        };

        const response = await client.sendMessage(sendParams);
        return response;
    }, [agentUrl, messages, getMessageHistory, contextId, getAccessToken]);

    // Стриминговая отправка сообщения (старая схема с TaskSendParams)
    const sendMessageStream = useCallback(async (content: string) => {
        const client = new A2AClient(agentUrl!, window.fetch.bind(window), getAccessToken);
        const taskId = uuidv4();
        const messageId = uuidv4();

        // Получаем историю сообщений
        const messageHistory = getMessageHistory(messages);

        // Создаем message объект с условным включением contextId
        const streamMessage: Message = {
            messageId: messageId,
            role: "user",
            parts: [{ text: content, kind: "text" }],
            kind: "message",
            ...(contextId && { contextId: contextId })
        };

        const sendParams: TaskSendParams = {
            id: taskId,
            message: streamMessage,
            metadata: {
                messageHistory: messageHistory,
                historyCount: messageHistory.length,
                sessionInfo: {
                    totalMessages: messages.length + 1,
                    timestamp: new Date().toISOString(),
                    userAgent: navigator.userAgent
                }
            }
        };

        console.log("Отправляем задачу (стриминг режим) с историей:", {
            taskId,
            messageId,
            historyCount: messageHistory.length,
            isStreaming: true,
            contextId: contextId
        });

        console.log("TaskSendParams:", JSON.stringify(sendParams, null, 2));

        const agentResponse = "";
        let agentMessageId: number | null = null;
        let accumulatedText = "";
        const accumulatedArtifacts: Artifact[] = [];
        const accumulatedParts: Part[] = [];

        try {
            // Создаем временное сообщение агента для стриминга
            setMessages(prev => {
                const agentMessage: ChatMessage = {
                    id: prev.length + 1,
                    sender: "agent",
                    content: "▋", // Начинаем с курсора
                    senderName: "Assistant",
                    timestamp: new Date(),
                    artifacts: [],
                    parts: []
                };
                agentMessageId = agentMessage.id;
                return [...prev, agentMessage];
            });

            // Обрабатываем стрим
            for await (const event of client.sendTaskSubscribe(sendParams)) {
                console.log("Streaming event:", event);

                if (event && typeof event === 'object') {
                    let newTextChunk = "";

                    // Обработка TaskStatusUpdateEvent
                    if ('status' in event && event.status) {
                        const status = event.status as any;
                        if (status.message && status.message.parts) {
                            const textParts = status.message.parts
                                .filter((part: any) => part.kind === "text")
                                .map((part: any) => part.text)
                                .join("");

                            if (textParts) {
                                newTextChunk = textParts;
                            }
                        }
                    }

                    // Обработка TaskArtifactUpdateEvent
                    if ('artifact' in event && event.artifact) {
                        const artifact = event.artifact as any;

                        // Добавляем artifact к накопленным
                        const existingIndex = accumulatedArtifacts.findIndex(a => a.artifactId === artifact.artifactId);
                        if (existingIndex >= 0) {
                            accumulatedArtifacts[existingIndex] = artifact;
                        } else {
                            accumulatedArtifacts.push(artifact);
                        }

                        // Обновляем сообщение с новыми artifacts
                        if (agentMessageId) {
                            setMessages(prev =>
                                prev.map(msg =>
                                    msg.id === agentMessageId
                                        ? { ...msg, artifacts: [...accumulatedArtifacts] }
                                        : msg
                                )
                            );
                        }

                        // Извлекаем текст из artifact для печатания
                        if (artifact.parts) {
                            const textParts = artifact.parts
                                .filter((part: any) => part.kind === "text")
                                .map((part: any) => part.text)
                                .join("");

                            if (textParts) {
                                newTextChunk = textParts;
                            }
                        }
                    }

                    // Если получили новый текст, добавляем его к накопленному
                    if (newTextChunk && newTextChunk !== accumulatedText) {
                        // Останавливаем предыдущую анимацию
                        stopTyping();

                        // Определяем новую часть текста
                        let textToAdd = "";
                        if (newTextChunk.startsWith(accumulatedText)) {
                            textToAdd = newTextChunk.substring(accumulatedText.length);
                        } else {
                            textToAdd = newTextChunk;
                            accumulatedText = "";
                        }

                        accumulatedText += textToAdd;

                        // Запускаем анимацию печатания для нового текста
                        if (agentMessageId && textToAdd) {
                            simulateTyping(agentMessageId, accumulatedText);
                        }
                    }

                    // Проверяем завершение
                    if ('final' in event && event.final) {
                        console.log("Streaming completed");
                        // Завершаем анимацию и показываем полный текст с artifacts
                        if (agentMessageId) {
                            stopTyping();
                            setMessages(prev =>
                                prev.map(msg =>
                                    msg.id === agentMessageId
                                        ? {
                                            ...msg,
                                            content: accumulatedText,
                                            artifacts: accumulatedArtifacts.length > 0 ? accumulatedArtifacts : undefined,
                                            parts: accumulatedParts.length > 0 ? accumulatedParts : undefined
                                        }
                                        : msg
                                )
                            );
                        }
                        break;
                    }
                }
            }
        } catch (error) {
            console.error("Streaming error:", error);
            // Останавливаем анимацию и показываем ошибку
            stopTyping();
            if (agentMessageId) {
                setMessages(prev =>
                    prev.map(msg =>
                        msg.id === agentMessageId
                            ? { ...msg, content: `Streaming error: ${error instanceof Error ? error.message : String(error)}` }
                            : msg
                    )
                );
            }
        }

        return accumulatedText;
    }, [agentUrl, messages, getMessageHistory, simulateTyping, stopTyping]);

    // Streaming with Parts support
    const sendMessageStreamWithParts = useCallback(async (parts: Part[]): Promise<string> => {
        const client = new A2AClient(agentUrl!, window.fetch.bind(window), getAccessToken);
        const taskId = uuidv4();
        const messageId = uuidv4();

        const messageHistory = getMessageHistory(messages);

        const streamMessage: Message = {
            messageId: messageId,
            role: "user",
            parts: parts,
            kind: "message",
            ...(contextId && { contextId: contextId })
        };

        const sendParams: TaskSendParams = {
            id: taskId,
            message: streamMessage,
            metadata: {
                messageHistory: messageHistory,
                historyCount: messageHistory.length
            }
        };

        let agentMessageId: number | null = null;
        let accumulatedText = "";
        const accumulatedArtifacts: Artifact[] = [];
        const accumulatedParts: Part[] = [];

        try {
            setMessages(prev => {
                const agentMessage: ChatMessage = {
                    id: prev.length + 1,
                    sender: "agent",
                    content: "▋",
                    senderName: "Assistant",
                    timestamp: new Date(),
                    artifacts: [],
                    parts: []
                };
                agentMessageId = agentMessage.id;
                return [...prev, agentMessage];
            });

            for await (const event of client.sendTaskSubscribe(sendParams)) {
                if (event && typeof event === 'object') {
                    let newTextChunk = "";

                    if ('status' in event && event.status) {
                        const status = event.status as any;
                        if (status.message && status.message.parts) {
                            const textParts = status.message.parts
                                .filter((part: any) => part.kind === "text")
                                .map((part: any) => part.text)
                                .join("");

                            if (textParts) {
                                newTextChunk = textParts;
                            }
                        }
                    }

                    if ('artifact' in event && event.artifact) {
                        const artifact = event.artifact as any;
                        const existingIndex = accumulatedArtifacts.findIndex(a => a.artifactId === artifact.artifactId);
                        if (existingIndex >= 0) {
                            accumulatedArtifacts[existingIndex] = artifact;
                        } else {
                            accumulatedArtifacts.push(artifact);
                        }

                        if (agentMessageId) {
                            setMessages(prev =>
                                prev.map(msg =>
                                    msg.id === agentMessageId
                                        ? { ...msg, artifacts: [...accumulatedArtifacts] }
                                        : msg
                                )
                            );
                        }
                    }

                    if ('parts' in event && Array.isArray(event.parts)) {
                        event.parts.forEach((part: any) => {
                            if (part.kind === "text" && part.text) {
                                newTextChunk += part.text;
                            }
                            accumulatedParts.push(part);
                        });

                        // Update parts in the message (for file/data parts display)
                        if (agentMessageId) {
                            setMessages(prev =>
                                prev.map(msg =>
                                    msg.id === agentMessageId
                                        ? { ...msg, parts: [...accumulatedParts] }
                                        : msg
                                )
                            );
                        }
                    }

                    const textToAdd = newTextChunk.substring(accumulatedText.length);
                    if (textToAdd) {
                        accumulatedText = newTextChunk;

                        if (agentMessageId && textToAdd) {
                            simulateTyping(agentMessageId, accumulatedText);
                        }
                    }

                    if ('final' in event && event.final) {
                        stopTyping();
                        if (agentMessageId) {
                            setMessages(prev =>
                                prev.map(msg =>
                                    msg.id === agentMessageId
                                        ? {
                                            ...msg,
                                            content: accumulatedText,
                                            artifacts: accumulatedArtifacts.length > 0 ? accumulatedArtifacts : undefined,
                                            parts: accumulatedParts.length > 0 ? accumulatedParts : undefined
                                        }
                                        : msg
                                )
                            );
                        }
                        break;
                    }
                }
            }
        } catch (error) {
            console.error("Streaming error:", error);
            stopTyping();
            if (agentMessageId) {
                setMessages(prev =>
                    prev.map(msg =>
                        msg.id === agentMessageId
                            ? { ...msg, content: `Streaming error: ${error instanceof Error ? error.message : String(error)}` }
                            : msg
                    )
                );
            }
        }

        return accumulatedText;
    }, [agentUrl, messages, getMessageHistory, simulateTyping, stopTyping, contextId]);

    const sendMessage = useCallback(async (parts: Part[]) => {
        if (parts.length === 0 || isLoading || !agentUrl) return;

        // Останавливаем любую текущую анимацию печатания
        stopTyping();

        // Extract text content for display
        const textContent = parts
            .filter(p => p.kind === "text")
            .map(p => (p as any).text)
            .join("\n");

        const userMessage: ChatMessage = {
            id: messages.length + 1,
            sender: "user",
            content: textContent || "[Files attached]",
            senderName: "You",
            timestamp: new Date(),
            parts: parts
        };

        // Добавляем сообщение пользователя к истории
        const updatedMessages = [...messages, userMessage];
        setMessages(updatedMessages);
        setIsLoading(true);

        try {
            if (isStreamingEnabled) {
                await sendMessageStreamWithParts(parts);
            } else {
                const responseMessage = await sendMessageSyncWithParts(parts);

                // Extract text from response parts
                let responseText = "No response";
                let responseArtifacts: Artifact[] = [];
                let responseParts: Part[] = [];

                if (responseMessage) {
                    if ('parts' in responseMessage && Array.isArray(responseMessage.parts)) {
                        responseParts = responseMessage.parts;
                        const textParts = responseMessage.parts
                            .filter((part: any) => part.kind === "text")
                            .map((part: any) => part.text)
                            .join("");
                        if (textParts) responseText = textParts;
                    }
                    if ('artifacts' in responseMessage && Array.isArray(responseMessage.artifacts)) {
                        responseArtifacts = responseMessage.artifacts;
                    }
                }

                setMessages(prev => {
                    const agentMessage: ChatMessage = {
                        id: prev.length + 1,
                        sender: "agent",
                        content: responseText,
                        senderName: "Assistant",
                        timestamp: new Date(),
                        artifacts: responseArtifacts.length > 0 ? responseArtifacts : undefined,
                        parts: responseParts.length > 0 ? responseParts : undefined
                    };
                    return [...prev, agentMessage];
                });
            }
        } catch (error) {
            console.error("A2A Client Error:", error);
            stopTyping();
            setMessages(prev => {
                const errorMessage: ChatMessage = {
                    id: prev.length + 1,
                    sender: "agent",
                    content: `Error: ${error instanceof Error ? error.message : String(error)}`,
                    senderName: "Assistant",
                    timestamp: new Date()
                };
                return [...prev, errorMessage];
            });
        } finally {
            setIsLoading(false);
        }
    }, [isLoading, agentUrl, messages, isStreamingEnabled, sendMessageSync, sendMessageStream, stopTyping]);

    return {
        messages,
        isLoading,
        messagesEndRef,
        scrollToBottom,
        sendMessage,
        setMessages
    };
};
