import React, { useState, useEffect, useRef, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { FileUpload, FileAttachment } from "@/components/common/FileUpload";
import { Progress } from "@/components/ui/progress";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
    CheckCircle2, AlertCircle, Loader2, FileText, BarChart3, Mail,
    Download, Globe, ChevronRight, Wifi
} from "lucide-react";
import { AgentCard } from "@/a2a/schema";
import { A2AClient } from "@/a2a/client";
import { uploadMultipleFilesWithSignedUrl } from "@/lib/signedUrlUpload";

// --- Types ---

interface WorkflowPageProps {
    selectedAgent: AgentCard | null;
    getAccessToken?: () => Promise<string>;
}

type Stage = {
    number: number;
    name: string;
    description: string;
    icon: React.ReactNode;
    status: "pending" | "in-progress" | "completed" | "error";
    message?: string;
    progress?: number;
    startTime?: number;
    endTime?: number;
    duration?: number;
};

type Results = {
    success: boolean;
    pdf_count: number;
    records_extracted: number;
    employee_count: number;
    savings_summary?: {
        summary: {
            total_issues: number;
            total_cost: number;
            monthly_savings: number;
            annual_savings: number;
        };
        months_analyzed: number;
        categories: {
            [key: string]: { count: number; total_cost: number };
        };
    };
    files?: Record<string, string | null>;
    download_urls?: Record<string, string | null>;
    processing_time: number;
};

// --- Country / vendor data ---

const COUNTRIES = [
    { value: "United States of America",      label: "United States of America" },
    { value: "Germany",                       label: "Germany" },
    { value: "Brazil",                        label: "Brazil" },
    { value: "Poland",                        label: "Poland" },
];

const VENDORS_BY_COUNTRY: Record<string, { value: string; label: string }[]> = {
    "United States of America": [
        { value: "att",     label: "AT&T" },
        { value: "verizon", label: "Verizon" },
    ],
    Germany: [
        { value: "datanet",    label: "Datanet" },
        { value: "telekom",    label: "Telekom" },
        { value: "servicenow", label: "ServiceNow" },
        { value: "vodafone",   label: "Vodafone" },
    ],
    Brazil: [
        { value: "vivo",    label: "Vivo" },
    ],
    Poland: [
        { value: "faktura",  label: "Faktura" },
    ],
};

// Currency info per country — used to show the correct symbol on savings figures.
const COUNTRY_CURRENCY: Record<string, { symbol: string; locale: string }> = {
    "United States of America": { symbol: "$",  locale: "en-US" },
    Germany:                     { symbol: "€",  locale: "de-DE" },
    Brazil:                      { symbol: "R$", locale: "pt-BR" },
    Poland:                      { symbol: "z\u0142", locale: "pl-PL" },
};

// --- Progress estimator ---

function estimateProgress(statusText: string): number {
    const lower = statusText.toLowerCase();
    if (lower.includes("complete") || lower.includes("done") || lower.includes("finished")) return 95;
    if (lower.includes("saving") || lower.includes("writing") || lower.includes("export")) return 80;
    if (lower.includes("processing") || lower.includes("analyzing") || lower.includes("running")) return 60;
    if (lower.includes("extracting") || lower.includes("loading") || lower.includes("querying")) return 40;
    return 20;
}

// --- Component ---

export default function WorkflowPage({ selectedAgent, getAccessToken }: WorkflowPageProps) {

    const [selectedCountry, setSelectedCountry] = useState<string>("");
    const [selectedVendor,  setSelectedVendor]  = useState<string>("");
    const [pdfFiles,  setPdfFiles]  = useState<FileAttachment[]>([]);
    const [employeeScope, setEmployeeScope] = useState<"global" | "country">("global");
    const [isProcessing,  setIsProcessing]  = useState(false);
    const [jobId, setJobId] = useState<string | null>(null);

    const [stages, setStages] = useState<Stage[]>([
        { number: 1, name: "PDF to CSV Extraction",            description: "Extracting invoice data",        icon: <FileText  className="h-5 w-5" />, status: "pending" },
        { number: 2, name: "Data Cleaning & Validation",       description: "Normalising & deduplicating",    icon: <BarChart3 className="h-5 w-5" />, status: "pending" },
        { number: 3, name: "Business Logic & Inactive Detection", description: "Running cost & inactive user queries",   icon: <Globe     className="h-5 w-5" />, status: "pending" },
        { number: 4, name: "Reports & Email Alerts",           description: "Generating output files",        icon: <Mail      className="h-5 w-5" />, status: "pending" },
    ]);

    const [results, setResults] = useState<Results | null>(null);

    // --- Refs for cleanup on page unload ---
    const jobIdRef = useRef<string | null>(null);
    const isProcessingRef = useRef(false);

    // Keep refs in sync with state
    useEffect(() => { jobIdRef.current = jobId; }, [jobId]);
    useEffect(() => { isProcessingRef.current = isProcessing; }, [isProcessing]);

    // Cancel the running job on the backend and clean up files
    const cancelRunningJob = useCallback((jid: string | null, agentUrl: string | undefined) => {
        if (!jid || !agentUrl) return;
        const url = `${agentUrl}/cancel/${jid}`;
        fetch(url, { method: "POST" }).catch(() => {});
    }, []);

    // Auto-cancel job on page reload/close
    // Jobs are cancelled when user reloads or closes the tab to prevent orphaned jobs
    // Tab switching does NOT cancel - jobs continue running in background
    useEffect(() => {
        const handleBeforeUnload = () => {
            // Only cancel if job is actively processing
            if (isProcessingRef.current && jobIdRef.current) {
                cancelRunningJob(jobIdRef.current, selectedAgent?.url);
            }
        };

        // Note: visibilitychange is NOT used - we want jobs to continue when user switches tabs
        // Only cancel on actual page unload (reload/close)
        window.addEventListener("beforeunload", handleBeforeUnload);

        return () => {
            window.removeEventListener("beforeunload", handleBeforeUnload);
        };
    }, [selectedAgent?.url, cancelRunningJob]);

    // --- Stage helpers ---

    const updateStage = (num: number, status: Stage["status"], message?: string, progress?: number) => {
        setStages(prev => prev.map(s => {
            if (s.number !== num) return s;
            const u: Stage = { ...s, status, message };
            if (progress !== undefined) u.progress = progress;
            if (status === "in-progress" && !s.startTime) u.startTime = Date.now();
            if ((status === "completed" || status === "error") && s.startTime) {
                u.endTime  = Date.now();
                u.duration = (Date.now() - s.startTime) / 1000;
                if (status === "completed") u.progress = 100;
            }
            return u;
        }));
    };

    const resetStages = () => {
        setStages(prev => prev.map(s => ({
            ...s, status: "pending" as const, message: undefined,
            progress: undefined, startTime: undefined, endTime: undefined, duration: undefined,
        })));
    };

    // --- Polling-based Job Status Checker ---

    const pollJobUntilComplete = async (
        jobId: string,
        agentUrl: string,
        onProgress?: (status: any) => void
    ): Promise<any> => {
        const maxPolls = 180;  // Max 30 minutes (180 polls × 10s)
        const pollIntervalMs = 10000;  // Poll every 10 seconds
        
        console.log(`[POLLING] Starting job status polling for ${jobId}`);
        
        for (let attempt = 1; attempt <= maxPolls; attempt++) {
            try {
                // 1. Fetch current job status
                const headers: HeadersInit = { 'Content-Type': 'application/json' };
                
                if (getAccessToken) {
                    try {
                        const token = await getAccessToken();
                        if (token) headers['Authorization'] = `Bearer ${token}`;
                    } catch (err) {
                        console.warn('[POLLING] Auth token failed:', err);
                    }
                }
                
                const response = await fetch(`${agentUrl}/jobs/${jobId}`, { headers });
                
                if (!response.ok) {
                    console.warn(`[POLLING] Status ${response.status} on attempt ${attempt}`);
                    if (response.status === 404 && attempt < 5) {
                        // Job might not be created yet, retry
                        await new Promise(resolve => setTimeout(resolve, pollIntervalMs));
                        continue;
                    }
                    throw new Error(`Job status check failed: ${response.status}`);
                }
                
                const data = await response.json();
                console.log(`[POLLING] Attempt ${attempt}/${maxPolls}:`, {
                    status: data.status,
                    phase: data.current_phase
                });
                
                // 2. Update UI with progress
                if (onProgress) {
                    onProgress(data);
                }
                
                // 3. Check if job is complete
                if (data.status === "COMPLETED") {
                    console.log('[POLLING] ✅ Job completed successfully');
                    return data.results;
                }
                
                if (data.status === "FAILED") {
                    console.error('[POLLING] ❌ Job failed:', data.error_message);
                    throw new Error(data.error_message || "Job processing failed");
                }
                
                if (data.status === "CANCELLED") {
                    console.warn('[POLLING] 🚫 Job was cancelled by user');
                    throw new Error("Job was cancelled");
                }
                
                // 4. Still processing, wait and poll again
                await new Promise(resolve => setTimeout(resolve, pollIntervalMs));
                
            } catch (error) {
                if (attempt >= maxPolls) {
                    console.error('[POLLING] Max attempts reached');
                    throw error;
                }
                
                // Retry on network errors
                console.warn(`[POLLING] Error on attempt ${attempt}, retrying:`, error);
                await new Promise(resolve => setTimeout(resolve, pollIntervalMs));
            }
        }
        
        throw new Error('Job polling timed out after 30 minutes');
    };

    // --- Pipeline ---

    const handleRunPipeline = async () => {
        if (!selectedAgent?.url) { alert("No agent selected."); return; }
        if (pdfFiles.length === 0) { alert("Please upload at least one invoice PDF."); return; }
        if (isProcessing) return; // guard against double-click / React double-invoke

        // Lock the UI immediately so no second invocation can sneak through while we await.
        setIsProcessing(true); setResults(null); resetStages();

        // Silently verify Databricks is reachable before starting — user never sees this.
        try {
            const ping = await fetch(`${selectedAgent.url}/databricks/ping`);
            const pingData = await ping.json();
            if (!pingData.success) {
                alert(`Unable to reach Databricks: ${pingData.message ?? "Connection failed"}. Please contact your admin.`);
                setIsProcessing(false);
                return;
            }
        } catch {
            alert("Unable to reach the backend. Please check the agent is running.");
            setIsProcessing(false);
            return;
        }

        try {
            updateStage(1, "in-progress", "Uploading PDFs…", 5);
            const files      = pdfFiles.map(fa => fa.file);
            const uploadData = await uploadMultipleFilesWithSignedUrl(
                selectedAgent.url, files, undefined,
                (_, pct) => updateStage(1, "in-progress", `Uploading… ${pct.toFixed(0)}%`, Math.round(pct * 0.15)),
                false,
            );
            const uploadedPaths = uploadData.files.map((f: any) => f.filePath);
            const currentJobId  = uploadData.jobId;
            setJobId(currentJobId);

            // Upload done, now submitting job - Stage 1 continues (PDF extraction not done yet)
            updateStage(1, "in-progress", "Submitting job to backend...", 15);

            const countryLabel = COUNTRIES.find(c => c.value === selectedCountry)?.label ?? selectedCountry;
            const vendorLabel  = (VENDORS_BY_COUNTRY[selectedCountry] ?? VENDORS_BY_COUNTRY.unknown)
                .find(v => v.value === selectedVendor)?.label ?? selectedVendor;

            const messageText =
                `Process these invoice PDFs and analyze with Databricks employee data.\n\n` +
                `Country: ${countryLabel}\nVendor/Carrier: ${selectedVendor}\n` +
                `PDF files:\n${uploadedPaths.map((p: string) => `- ${p}`).join("\n")}\n\n` +
                `Important: Call invoice_pdf_to_tables for each PDF path listed above.\n\n` +
                `Employee data source: DATABRICKS\n` +
                `Use the load_databricks_employee_data tool. Do NOT ask for a CSV.\n`;

            // Trigger backend processing via upload/complete endpoint
            await fetch(`${selectedAgent.url}/upload/complete`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    job_id: currentJobId,
                    success: true,
                    trigger_orchestrator: true,
                    orchestrator_message: messageText
                })
            });

            console.log('[UI] Job submitted, starting polling...');
            
            // Start all stages as running immediately
            updateStage(1, "in-progress", "Processing...", 10);
            updateStage(2, "in-progress", "Waiting...", 0);
            updateStage(3, "in-progress", "Waiting...", 0);
            updateStage(4, "in-progress", "Waiting...", 0);

            // Poll for job completion
            const results = await pollJobUntilComplete(
                currentJobId,
                selectedAgent.url
            );

            // Display results
            if (results) {
                setResults({
                    success: true,
                    pdf_count: pdfFiles.length,
                    records_extracted: results.records_extracted || 0,
                    employee_count: results.employee_count || 0,
                    savings_summary: results.savings_summary,
                    files: results.files,
                    download_urls: results.download_urls,
                    processing_time: results.processing_time || 0,
                });
                console.log("[UI] ✅ Analysis results received:", results);
                
                // Mark all stages as completed
                updateStage(1, "completed", "PDF extraction completed");
                updateStage(2, "completed", "Data cleaning completed");
                updateStage(3, "completed", "Analysis completed");
                updateStage(4, "completed", "Results displayed", 100);
            } else {
                setResults({
                    success: true,
                    pdf_count: pdfFiles.length,
                    records_extracted: 0,
                    employee_count: 0,
                    processing_time: 0,
                });
                console.warn("[UI] ⚠️ No results returned from backend");
                
                // Mark all stages as completed
                updateStage(1, "completed", "Completed");
                updateStage(2, "completed", "Completed");
                updateStage(3, "completed", "Completed");
                updateStage(4, "completed", "Analysis complete", 100);
            }

            // Don't cleanup immediately - let user download results first
            // Cleanup will happen on page unload or when user starts a new job
            setPdfFiles([]);

        } catch (err) {
            const msg = err instanceof Error ? err.message : "Unknown error";
            const activeIdx = stages.findIndex(s => s.status === "in-progress");
            updateStage(activeIdx !== -1 ? stages[activeIdx].number : 1, "error", msg);
            alert(`Pipeline failed: ${msg}`);
        } finally {
            setIsProcessing(false);
        }
    };

    // --- Derived state ---

    const vendorOptions    = selectedCountry ? (VENDORS_BY_COUNTRY[selectedCountry] ?? []) : [];
    const currencySymbol   = COUNTRY_CURRENCY[selectedCountry]?.symbol ?? "$";
    const currencyLocale   = COUNTRY_CURRENCY[selectedCountry]?.locale ?? "en-US";
    const hasSelection     = selectedCountry !== "" && selectedVendor !== "";
    const canRun        = pdfFiles.length > 0 && !isProcessing && hasSelection;
    const anyRunning    = stages.some(s => s.status === "in-progress");
    const allDone       = stages.every(s => s.status === "completed");
    const anyError      = stages.some(s => s.status === "error");

    // --- Stage card helpers ---

    const stageCardClass = (s: Stage) => {
        if (s.status === "completed")   return "border-green-500  bg-green-50  dark:bg-green-950/40";
        if (s.status === "in-progress") return "border-blue-500   bg-blue-50   dark:bg-blue-950/40";
        if (s.status === "error")       return "border-red-500    bg-red-50    dark:bg-red-950/40";
        return "border-border";
    };

    const stageIcon = (s: Stage) => {
        if (s.status === "completed")   return <CheckCircle2 className="h-6 w-6 text-green-500" />;
        if (s.status === "in-progress") return <Loader2      className="h-6 w-6 text-blue-500 animate-spin" />;
        if (s.status === "error")       return <AlertCircle  className="h-6 w-6 text-red-500" />;
        return <div className="h-6 w-6 text-muted-foreground">{s.icon}</div>;
    };

    const openDownload = (url: string | null | undefined) => {
        if (url && selectedAgent?.url) window.open(`${selectedAgent.url}${url}`, "_blank");
    };

    const downloadEmployeeFiltered = () => {
        if (!selectedAgent?.url || !jobId) return;
        const country = COUNTRIES.find(c => c.value === selectedCountry)?.label ?? selectedCountry;
        window.open(`${selectedAgent.url}/output/employee-only-filtered?country=${encodeURIComponent(country)}&job_id=${encodeURIComponent(jobId)}`, "_blank");
    };

    // ─── JSX ─────────────────────────────────────────────────────────────────

    return (
        <div className="h-full overflow-y-auto">
            <div className="max-w-5xl mx-auto px-6 py-8 space-y-6">

                {/* Header */}
                <div className="text-center space-y-1">
                    <h1 className="text-3xl font-bold text-primary flex items-center justify-center gap-2">
                        <Wifi className="h-8 w-8" />
                        Wireless Invoice Analyser
                    </h1>
                    <p className="text-muted-foreground">AI-Powered Mobile Invoice Analysis &amp; Fraud Detection</p>
                </div>

                {/* SECTION 1: Pipeline Tracker */}
                <Card>
                    <CardHeader className="pb-3">
                        <CardTitle className="text-base font-semibold flex items-center gap-2">
                            🔄 4-Stage Pipeline
                            {anyRunning && <span className="text-xs text-blue-500 font-normal animate-pulse">Running…</span>}
                            {allDone    && <span className="text-xs text-green-500 font-normal">Complete ✓</span>}
                            {anyError   && <span className="text-xs text-red-500 font-normal">Error</span>}
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                            {stages.map((s, i) => (
                                <div key={s.number} className="flex items-stretch gap-0">
                                    <div className={`flex-1 p-3 border rounded-lg space-y-2 transition-all duration-300 ${stageCardClass(s)}`}>
                                        <div className="flex items-center justify-between">
                                            <span className="text-xs font-semibold text-muted-foreground">Stage {s.number}</span>
                                            {stageIcon(s)}
                                        </div>
                                        <div className="text-sm font-medium leading-tight">{s.name}</div>
                                        <div className="text-xs text-muted-foreground">{s.description}</div>

                                        {(s.status === "in-progress" || s.status === "completed") && (
                                            <Progress
                                                value={s.status === "completed" ? 100 : (s.progress ?? 20)}
                                                className="h-1.5"
                                            />
                                        )}

                                        {s.status === "in-progress" && s.message && (
                                            <p className="text-xs text-blue-600 dark:text-blue-400 line-clamp-2 leading-tight">{s.message}</p>
                                        )}
                                        {s.status === "completed" && s.duration !== undefined && (
                                            <p className="text-xs text-green-600 dark:text-green-400">✓ {s.duration.toFixed(1)}s</p>
                                        )}
                                        {s.status === "error" && s.message && (
                                            <p className="text-xs text-red-600 dark:text-red-400 line-clamp-2">{s.message}</p>
                                        )}
                                    </div>
                                    {i < stages.length - 1 && (
                                        <div className="hidden md:flex items-center -mx-1.5 z-10">
                                            <ChevronRight className="h-4 w-4 text-muted-foreground/40" />
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    </CardContent>
                </Card>


                {/* SECTION 2: Country & Vendor */}
                <Card>
                    <CardHeader className="pb-3">
                        <CardTitle className="text-base font-semibold">🌍 Select Country &amp; Carrier</CardTitle>
                        <CardDescription>
                            Select the country and carrier whose invoices you are uploading.
                            This labels the output reports correctly.
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div className="space-y-1.5">
                                <label className="text-sm font-medium">Country</label>
                                <select
                                    value={selectedCountry}
                                    onChange={e => { setSelectedCountry(e.target.value); setSelectedVendor(""); }}
                                    disabled={isProcessing}
                                    className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
                                >
                                    <option value="" disabled>— Select a country —</option>
                                    {COUNTRIES.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
                                </select>
                            </div>
                            <div className="space-y-1.5">
                                <label className="text-sm font-medium">Carrier / Vendor</label>
                                <select
                                    value={selectedVendor}
                                    onChange={e => setSelectedVendor(e.target.value)}
                                    disabled={isProcessing || !selectedCountry}
                                    className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
                                >
                                    <option value="" disabled>— Select a vendor —</option>
                                    {vendorOptions.map(v => <option key={v.value} value={v.value}>{v.label}</option>)}
                                </select>
                            </div>
                        </div>

                        {selectedCountry !== "" && (
                            <Alert>
                                <AlertDescription className="text-sm">
                                    📍 <strong>{COUNTRIES.find(c => c.value === selectedCountry)?.label}</strong>
                                    {selectedVendor !== "" && (
                                        <> · <strong>{vendorOptions.find(v => v.value === selectedVendor)?.label}</strong></>
                                    )}
                                    <span className="text-muted-foreground ml-2">
                                        (Databricks loads all global employee data for now)
                                    </span>
                                </AlertDescription>
                            </Alert>
                        )}
                    </CardContent>
                </Card>

                {/* SECTION 3: Upload PDFs — only shown after country & vendor are selected */}
                {hasSelection && (
                <Card>
                    <CardHeader className="pb-3">
                        <CardTitle className="text-base font-semibold">📄 Upload Invoice PDFs</CardTitle>
                        <CardDescription>
                            Upload monthly invoice PDF files from your wireless carrier. Up to 6 files, max 200 MB each.
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        <FileUpload
                            files={pdfFiles}
                            onFilesSelected={setPdfFiles}
                            onFileRemove={idx => setPdfFiles(prev => prev.filter((_, i) => i !== idx))}
                            accept=".pdf"
                            maxFiles={6}
                            maxSizeMB={200}
                            disabled={isProcessing}
                        />
                    </CardContent>
                </Card>
                )}

                {/* SECTION 4: Run Button */}
                <div className="flex flex-col items-center gap-2">
                    <Button
                        size="lg"
                        onClick={handleRunPipeline}
                        disabled={!canRun}
                        className="px-10 py-6 text-base font-semibold"
                    >
                        {isProcessing
                            ? <><Loader2 className="h-5 w-5 mr-2 animate-spin" />Processing Pipeline…</>
                            : <>Run Analysis Pipeline →</>}
                    </Button>
                    {!isProcessing && pdfFiles.length > 0 && (
                        <p className="text-xs text-green-600">✓ {pdfFiles.length} PDF{pdfFiles.length !== 1 ? "s" : ""} ready</p>
                    )}
                </div>

                {/* SECTION 5: Results */}
                {results && results.success && (
                    <Card>
                        <CardHeader className="pb-3">
                            <CardTitle className="text-base font-semibold">📋 Analysis Results</CardTitle>
                            {results.savings_summary && (
                                <CardDescription>
                                    {results.savings_summary.months_analyzed} month(s) analysed ·{" "}
                                    {results.savings_summary.summary.total_issues} issues found ·{" "}
                                    Est. annual savings{" "}
                                    <strong className="text-green-600">
                                        {currencySymbol}{results.savings_summary.summary.annual_savings.toLocaleString(currencyLocale, { maximumFractionDigits: 0 })}
                                    </strong>
                                </CardDescription>
                            )}
                        </CardHeader>
                        <CardContent className="space-y-5">

                            {results.savings_summary && (
                                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                                    {[
                                        { label: "Total Issues",    value: results.savings_summary.summary.total_issues.toLocaleString(currencyLocale) },
                                        { label: "Monthly Savings", value: `${currencySymbol}${results.savings_summary.summary.monthly_savings.toLocaleString(currencyLocale, { maximumFractionDigits: 0 })}` },
                                        { label: "Annual Savings",  value: `${currencySymbol}${results.savings_summary.summary.annual_savings.toLocaleString(currencyLocale, { maximumFractionDigits: 0 })}`, green: true },
                                        { label: "Months Analysed", value: results.savings_summary.months_analyzed.toString() },
                                    ].map(m => (
                                        <div key={m.label} className="p-3 border rounded-lg text-center">
                                            <div className="text-xs text-muted-foreground mb-1">{m.label}</div>
                                            <div className={`text-xl font-bold ${(m as any).green ? "text-green-600" : ""}`}>{m.value}</div>
                                        </div>
                                    ))}
                                </div>
                            )}

                            <Tabs defaultValue="zero">
                                <TabsList className="grid w-full grid-cols-4">
                                    <TabsTrigger value="zero">
                                        Zero Usage
                                        {results.savings_summary?.categories?.zero_usage &&
                                            <span className="ml-1 text-xs opacity-70">({results.savings_summary.categories.zero_usage.count})</span>}
                                    </TabsTrigger>
                                    <TabsTrigger value="invoice">
                                        User Not Found
                                        {results.savings_summary?.categories?.invoice_only &&
                                            <span className="ml-1 text-xs opacity-70">({results.savings_summary.categories.invoice_only.count})</span>}
                                    </TabsTrigger>
                                    <TabsTrigger value="fraud">
                                        Inactive Users
                                        {results.savings_summary?.categories?.fraud &&
                                            <span className="ml-1 text-xs opacity-70">({results.savings_summary.categories.fraud.count})</span>}
                                    </TabsTrigger>
                                    <TabsTrigger value="employee">
                                        Employee Only
                                        {results.savings_summary?.categories?.employee_only &&
                                            <span className="ml-1 text-xs opacity-70">({results.savings_summary.categories.employee_only.count})</span>}
                                    </TabsTrigger>
                                </TabsList>

                                <TabsContent value="zero" className="space-y-3 pt-3">
                                    <Alert><AlertDescription>
                                        <strong>Zero Usage Users</strong> — Active personal/non-personal lines with no voice/data/SMS.
                                        These can be cancelled to save costs.
                                    </AlertDescription></Alert>
                                    <Button 
                                        onClick={() => openDownload(results.download_urls?.zero_usage)}
                                        disabled={!results.savings_summary?.categories?.zero_usage?.count || results.savings_summary.categories.zero_usage.count === 0}
                                    >
                                        <Download className="h-4 w-4 mr-2" />Download Zero Usage Report
                                    </Button>
                                    {(!results.savings_summary?.categories?.zero_usage?.count || results.savings_summary.categories.zero_usage.count === 0) && (
                                        <p className="text-sm text-muted-foreground py-2 text-center">No zero-usage cases found.</p>
                                    )}
                                </TabsContent>

                                <TabsContent value="invoice" className="space-y-3 pt-3">
                                    <Alert><AlertDescription>
                                        <strong>User Not Found</strong> — Numbers billed by carrier but not in the employee database.
                                        Could be ex-employees still being charged.
                                    </AlertDescription></Alert>
                                    <Button 
                                        onClick={() => openDownload(results.download_urls?.invoice_only)}
                                        disabled={!results.savings_summary?.categories?.invoice_only?.count || results.savings_summary.categories.invoice_only.count === 0}
                                    >
                                        <Download className="h-4 w-4 mr-2" />Download User Not Found Report
                                    </Button>
                                    {(!results.savings_summary?.categories?.invoice_only?.count || results.savings_summary.categories.invoice_only.count === 0) && (
                                        <p className="text-sm text-muted-foreground py-2 text-center">No user-not-found cases found.</p>
                                    )}
                                </TabsContent>

                                <TabsContent value="fraud" className="space-y-3 pt-3">
                                    <Alert><AlertDescription>
                                        <strong>Inactive Users</strong> — Inactive or terminated employees still generating charges.
                                        Requires immediate investigation.
                                    </AlertDescription></Alert>
                                    <Button 
                                        onClick={() => openDownload(results.download_urls?.fraud)}
                                        disabled={!results.savings_summary?.categories?.fraud?.count || results.savings_summary.categories.fraud.count === 0}
                                    >
                                        <Download className="h-4 w-4 mr-2" />Download Inactive Users Report
                                    </Button>
                                    {(!results.savings_summary?.categories?.fraud?.count || results.savings_summary.categories.fraud.count === 0) && (
                                        <p className="text-sm text-green-600 py-2 text-center font-medium">✓ No inactive user cases detected.</p>
                                    )}
                                </TabsContent>

                                <TabsContent value="employee" className="space-y-3 pt-3">
                                    <Alert><AlertDescription>
                                        <strong>Employee Only Users</strong> — Employees in the database with no invoice charges.
                                        Could be employees without phone assignments or recent hires.
                                    </AlertDescription></Alert>

                                    {/* Scope toggle */}
                                    <div className="flex flex-wrap items-center gap-4 p-3 border rounded-lg bg-muted/30">
                                        <span className="text-sm font-medium">Output scope:</span>
                                        <label className="flex items-center gap-1.5 cursor-pointer text-sm">
                                            <input type="radio" name="empScope" checked={employeeScope === "global"}
                                                onChange={() => setEmployeeScope("global")} className="accent-primary" />
                                            All countries (global)
                                        </label>
                                        <label className={`flex items-center gap-1.5 text-sm ${selectedCountry === "" ? "opacity-40 cursor-not-allowed" : "cursor-pointer"}`}>
                                            <input type="radio" name="empScope" checked={employeeScope === "country"}
                                                onChange={() => setEmployeeScope("country")}
                                                disabled={selectedCountry === ""} className="accent-primary" />
                                            {selectedCountry !== ""
                                                ? `${COUNTRIES.find(c => c.value === selectedCountry)?.label} only`
                                                : "Country-specific (select a country above first)"}
                                        </label>
                                    </div>

                                    {employeeScope === "global"
                                        ? <Button 
                                              onClick={() => openDownload(results.download_urls?.employee_only)}
                                              disabled={!results.savings_summary?.categories?.employee_only?.count || results.savings_summary.categories.employee_only.count === 0}
                                          >
                                              <Download className="h-4 w-4 mr-2" />Download Employee Only (Global)
                                          </Button>
                                        : <Button 
                                              onClick={downloadEmployeeFiltered}
                                              disabled={!results.savings_summary?.categories?.employee_only?.count || results.savings_summary.categories.employee_only.count === 0}
                                          >
                                              <Download className="h-4 w-4 mr-2" />
                                              Download Employee Only ({COUNTRIES.find(c => c.value === selectedCountry)?.label})
                                          </Button>
                                    }
                                    {(!results.savings_summary?.categories?.employee_only?.count || results.savings_summary.categories.employee_only.count === 0) && (
                                        <p className="text-sm text-muted-foreground py-2 text-center">All employees have invoice records.</p>
                                    )}
                                </TabsContent>
                            </Tabs>
                        </CardContent>
                    </Card>
                )}
            </div>
        </div>
    );
}
