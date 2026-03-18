# Streamlit-Style Workflow UI Implementation

## Overview
Successfully replaced the chat UI with a Streamlit-style file upload and stage-wise progress interface for the wireless contract analyzer.

## What Changed

### 1. **New Components Created**

#### `WorkflowPage.tsx` ([ui/src/app/pages/WorkflowPage.tsx](ui/src/app/pages/WorkflowPage.tsx))
- Complete replacement for the chat interface
- Implements Streamlit-style UI with:
  - **Workflow Selection**: PDF (full pipeline) vs CSV (quick mode)
  - **File Upload Sections**: Drag-and-drop file upload for PDFs/CSVs and employee data
  - **4-Stage Pipeline Visualization**: Real-time status tracking
  - **Results Dashboard**: Displays metrics and savings after completion

#### UI Components
- **Progress Bar** ([ui/src/components/ui/progress.tsx](ui/src/components/ui/progress.tsx))
- **Alert Component** ([ui/src/components/ui/alert.tsx](ui/src/components/ui/alert.tsx))

### 2. **Updated Files**

#### `TabContent.tsx` ([ui/src/components/layout/TabContent.tsx](ui/src/components/layout/TabContent.tsx))
- Replaced `ChatContainer` with `WorkflowPage` for the "chat" tab
- Integrated authentication token provider

#### `package.json` ([ui/package.json](ui/package.json))
- Added `@radix-ui/react-progress` dependency

---

## Features Implemented

### 📤 **File Upload Options**

#### **Option A: Upload PDFs (Full Pipeline)**
- Upload invoice PDFs (multiple files supported)
- Upload employee data CSV
- Triggers 4-stage pipeline with PDF extraction

#### **Option B: Upload CSVs (Quick Mode)**
- Upload pre-extracted invoice CSVs
- Upload employee data CSV
- Skips PDF extraction (saves ~10 minutes)

### 🔄 **4-Stage Pipeline**

| Stage | Name | Description | Status Indicators |
|-------|------|-------------|-------------------|
| 1 | PDF to CSV Extraction | Extracts MSISDN data from PDFs | 📄 Pending → 🔵 In Progress → ✅ Complete |
| 2 | Data Cleaning & Validation | Processes employee data | 👥 Pending → 🔵 In Progress → ✅ Complete |
| 3 | Business Logic & Fraud Detection | Analyzes data for fraud | 📊 Pending → 🔵 In Progress → ✅ Complete |
| 4 | Reports & Email Alerts | Generates reports and sends emails | 📧 Pending → 🔵 In Progress → ✅ Complete |

### 📊 **Results Dashboard**
Displays after successful pipeline execution:
- **Files Processed**: Count of PDFs/CSVs
- **Records Extracted**: Total invoice records
- **Employees Analyzed**: Employee count
- **Total Savings Opportunity**: Dollar amount from fraud detection

---

## How It Works

### **User Flow**

```
1. User logs in → A2A UI loads
2. Navigate to "Conversations" tab (displays WorkflowPage)
3. Select workflow: PDF or CSV mode
4. Upload files:
   - Invoice files (PDFs or CSVs)
   - Employee data CSV
5. Click "Run Analysis Pipeline"
6. Monitor real-time stage progress
7. View results dashboard
```

### **Backend Integration**

```typescript
// 1. Files are uploaded to agent
for (const file of files) {
  const path = await uploadFileToAgent(file, agentUrl);
  uploadedPaths.push(path);
}

// 2. A2A Client sends task with file references
const client = new A2AClient(agentUrl, fetch, getAccessToken);
const taskGenerator = client.sendTaskStream({
  parts: [
    { text: message },
    ...uploadedPaths.map(path => ({ file_uri: path }))
  ]
});

// 3. Stream events update stage status
for await (const event of taskGenerator) {
  if (event.type === 'status') {
    // Update UI stage progress
    updateStage(stageNumber, 'in-progress', event.payload.status);
  }
}
```

### **Communication with Phased Orchestrator**

The WorkflowPage communicates with the mobile-contract-agent's phased orchestrator:

1. **Uploads files** via `POST /upload` endpoint
2. **Sends task** via JSON-RPC `task/send` (streaming)
3. **Receives status updates** as the orchestrator executes each phase:
   - Phase 1: PDF extraction → Stage 1 update
   - Phase 2: Employee data loading → Stage 2 update
   - Phase 3: Report generation → Stage 3 update
   - Phase 4: Email notification → Stage 4 update
4. **Displays final results** from artifact events

---

## Installation & Setup

### 1. Install Dependencies

```powershell
cd ui
npm install
```

This will install the new `@radix-ui/react-progress` package.

### 2. Environment Configuration

Ensure your `.env.local` has the agent URL configured:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### 3. Start the Development Server

```powershell
npm run dev
```

Navigate to `http://localhost:3000` and log in.

---

## Testing the Workflow

### **Scenario 1: PDF Upload (Full Pipeline)**

1. Click **"Option A: Upload PDFs"**
2. Upload invoice PDFs:
   - E.g., `OCT_Bill.pdf`, `NOV_Bill.pdf`
3. Upload employee CSV:
   - E.g., `local_std_dwh.csv`
4. Click **"Run Analysis Pipeline"**
5. Watch stages progress from pending → in-progress → completed
6. View results dashboard

### **Scenario 2: CSV Upload (Quick Mode)**

1. Click **"Option B: Upload CSVs"**
2. Upload invoice CSVs:
   - E.g., `OCT_Invoice.csv`, `NOV_Invoice.csv`
3. Upload employee CSV:
   - E.g., `local_std_dwh.csv`
4. Click **"Run Analysis Pipeline"**
5. Stage 1 skips PDF extraction (faster!)
6. View results

---

## File Structure

```
ui/src/
├── app/
│   └── pages/
│       └── WorkflowPage.tsx          # NEW: Main workflow interface
├── components/
│   ├── common/
│   │   └── FileUpload.tsx            # Existing: Reused for file uploads
│   ├── layout/
│   │   └── TabContent.tsx            # MODIFIED: Uses WorkflowPage
│   └── ui/
│       ├── alert.tsx                 # NEW: Alert component
│       ├── progress.tsx              # NEW: Progress bar component
│       └── card.tsx                  # Existing: Used for cards
└── lib/
    ├── uploadFileToAgent.ts          # Existing: File upload utility
    └── env.ts                        # Existing: Environment config
```

---

## Customization

### **Modify Stage Names**

Edit the `stages` array in `WorkflowPage.tsx`:

```typescript
const [stages, setStages] = useState<Stage[]>([
  { number: 1, name: 'Your Custom Stage 1', icon: <YourIcon />, status: 'pending' },
  // ... more stages
]);
```

### **Change Color Scheme**

Update the gradient classes in the stage cards:

```typescript
className={`p-4 border rounded-lg ${
  stage.status === 'in-progress' ? 'bg-blue-50 dark:bg-blue-950' :
  // ... customize colors
}`}
```

### **Add More Metrics**

Extend the `Results` interface and dashboard:

```typescript
type Results = {
  // ... existing fields
  custom_metric: number;
};

// In Results Dashboard
<div className="p-4 bg-gradient-to-br from-purple-500 to-pink-600 rounded-lg text-white">
  <div className="text-3xl font-bold">{results.custom_metric}</div>
  <div className="text-sm opacity-90">Your Custom Metric</div>
</div>
```

---

## Differences from Streamlit Version

| Feature | Streamlit | Next.js |
|---------|-----------|---------|
| File Upload | `st.file_uploader()` | Drag-and-drop `FileUpload` component |
| Progress Bar | `st.progress()` | Radix UI `Progress` component |
| Stage Status | Markdown headers | Card-based with icons |
| Workflow Selection | Buttons | styled Button components |
| Results Display | `st.metric()` | Gradient cards with metrics |
| Real-time Updates | `st.empty()` + text updates | Event streaming with state updates |

---

## Troubleshooting

### **Issue: Files not uploading**
- Check agent is running on `http://localhost:8000`
- Verify `/upload` endpoint is accessible
- Check browser console for errors

### **Issue: Stages not progressing**
- Ensure agent's phased orchestrator is configured correctly
- Check that phase outputs contain "Stage X" or "STAGE X" keywords
- Verify streaming is enabled in agent config

### **Issue: Results not displaying**
- Check that agent returns artifact events with results
- Verify JSON structure matches `Results` interface
- Check browser console for parsing errors

---

## Next Steps

### **Recommended Enhancements**

1. **Add Download Reports Button**
   - Allow users to download generated Excel reports

2. **Add Email Configuration**
   - Let users specify email recipients

3. **Add History/Logs Tab**
   - Show previous pipeline runs

4. **Add Real-time Logs**
   - Display agent logs during processing

5. **Add Cancel Button**
   - Allow users to cancel running pipelines

### **Code Example: Download Reports**

```typescript
const handleDownloadReport = async () => {
  if (!results?.report_path) return;

  const response = await fetch(`${selectedAgent?.url}/download`, {
    method: 'POST',
    body: JSON.stringify({ file_path: results.report_path })
  });

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'analysis_report.xlsx';
  a.click();
};
```

---

## Summary

✅ **Completed:**
- Created Streamlit-style workflow UI
- Implemented file upload with drag-and-drop
- Added 4-stage pipeline visualization
- Integrated with A2A phased orchestrator
- Added results dashboard
- Maintained authentication and agent management

🔧 **Technical Stack:**
- Next.js 15 + React 19
- TypeScript
- Radix UI components
- Tailwind CSS
- A2A Client (JSON-RPC 2.0)

📦 **Dependencies Added:**
- `@radix-ui/react-progress@^1.2.1`

The UI now provides a user-friendly, non-technical interface for wireless contract analysis, matching the Streamlit workflow while leveraging Next.js performance and the A2A protocol for agent communication.
