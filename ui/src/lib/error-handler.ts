export function logErrorToBoundary(error: Error, errorInfo: React.ErrorInfo) {
  // Log error to console in development
  if (process.env.NODE_ENV === 'development') {
    console.error('Error caught by boundary:', error, errorInfo);
  }

  // In production, you might want to send this to a logging service
  // Example: sendToLoggingService(error, errorInfo);
}
