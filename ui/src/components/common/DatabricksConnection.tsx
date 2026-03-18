"use client";

import React, { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  CheckCircle2,
  AlertCircle,
  Loader2,
  ChevronDown,
  ChevronRight,
  Database,
  Eye,
  EyeOff,
  Zap,
} from "lucide-react";

// ─── Default Databricks config (matches .env.development) ──────────────────
const DEFAULTS = {
  host: "adb-4071335540424391.11.azuredatabricks.net",
  httpPath: "/sql/1.0/warehouses/916c447fdd11cd1e",
  catalog: "efdataonelh_prd",
  schema: "generaldiscovery_servicenow_r",
} as const;

// ─── Public types ───────────────────────────────────────────────────────────
export interface DatabricksConfig {
  host: string;
  httpPath: string;
  token: string;
  catalog: string;
  schema: string;
  countryFilter: string | null;
}

export type ConnectionStatus = "idle" | "testing" | "connected" | "error";

interface DatabricksConnectionProps {
  /** Called when Fetch Employee Data succeeds — passes the record count */
  onDataFetched?: (recordCount: number) => void;
  /** Expose the current config so the parent can send it with the A2A message */
  onConfigChange?: (config: DatabricksConfig | null) => void;
  /** Lock the UI while the pipeline is running */
  disabled?: boolean;
  /** Base URL of the agent server (for test-connection & fetch calls) */
  agentUrl?: string;
}

export function DatabricksConnection({
  onDataFetched,
  onConfigChange,
  disabled = false,
  agentUrl,
}: DatabricksConnectionProps) {
  // Token
  const [token, setToken] = useState("");
  const [showToken, setShowToken] = useState(false);

  // Advanced settings (collapsed by default)
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [host] = useState(DEFAULTS.host);
  const [httpPath] = useState(DEFAULTS.httpPath);
  const [catalog] = useState(DEFAULTS.catalog);
  const [schema] = useState(DEFAULTS.schema);

  // Country filter
  const [countryFilter, setCountryFilter] = useState<string>("all");

  // Connection status
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>("idle");
  const [connectionMessage, setConnectionMessage] = useState("");

  // Fetch status
  const [isFetching, setIsFetching] = useState(false);
  const [fetchedCount, setFetchedCount] = useState<number | null>(null);

  // ── Build config object ──────────────────────────────────────────────────
  const buildConfig = (): DatabricksConfig => ({
    host,
    httpPath,
    token,
    catalog,
    schema,
    countryFilter: countryFilter === "all" ? null : countryFilter,
  });

  // ── Test Connection ──────────────────────────────────────────────────────
  const handleTestConnection = async () => {
    if (!token.trim()) {
      setConnectionStatus("error");
      setConnectionMessage("Please enter a Databricks API Token");
      return;
    }

    setConnectionStatus("testing");
    setConnectionMessage("");

    try {
      if (agentUrl) {
        // Call the agent's test-databricks endpoint
        const resp = await fetch(`${agentUrl}/databricks/test`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token, host, http_path: httpPath, catalog, schema_name: schema }),
        });
        if (!resp.ok) throw new Error(`Server error: ${resp.status}`);
        const data = await resp.json();
        if (data.success) {
          setConnectionStatus("connected");
          setConnectionMessage(data.message || "Connected successfully");
        } else {
          setConnectionStatus("error");
          setConnectionMessage(data.message || "Connection failed");
        }
      } else {
        // Offline validation — just accept non-empty token
        await new Promise((r) => setTimeout(r, 600));
        setConnectionStatus("connected");
        setConnectionMessage("Token saved — connection will be verified when pipeline runs");
      }
    } catch (err: any) {
      setConnectionStatus("error");
      setConnectionMessage(err?.message || "Connection failed");
    }

    // Propagate config to parent
    onConfigChange?.(buildConfig());
  };

  // ── Fetch Employee Data ──────────────────────────────────────────────────
  const handleFetchData = async () => {
    if (connectionStatus !== "connected") {
      setConnectionStatus("error");
      setConnectionMessage("Test the connection first");
      return;
    }

    setIsFetching(true);
    try {
      if (agentUrl) {
        const cfg = buildConfig();
        const resp = await fetch(`${agentUrl}/databricks/fetch-employees`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            token: cfg.token,
            host: cfg.host,
            http_path: cfg.httpPath,
            catalog: cfg.catalog,
            schema_name: cfg.schema,
            country_filter: cfg.countryFilter,
          }),
        });

        if (!resp.ok) throw new Error(await resp.text());
        const data = await resp.json();
        const count = data.record_count ?? data.records ?? 0;
        setFetchedCount(count);
        onDataFetched?.(count);
      } else {
        // Offline stub — real fetch happens via A2A tool in the pipeline
        await new Promise((r) => setTimeout(r, 400));
        setFetchedCount(-1); // -1 = "will fetch at runtime"
        onDataFetched?.(-1);
      }
    } catch (err: any) {
      setConnectionMessage(err?.message || "Failed to fetch employee data");
    } finally {
      setIsFetching(false);
    }

    onConfigChange?.(buildConfig());
  };

  // When token or settings change, push config to parent
  const handleTokenChange = (val: string) => {
    setToken(val);
    setConnectionStatus("idle");
    setFetchedCount(null);
    onConfigChange?.(val ? { ...buildConfig(), token: val } : null);
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center gap-2 text-lg font-semibold">
        <Database className="h-5 w-5 text-primary" />
        Databricks Connection
      </div>

      {/* Info banner */}
      <Alert className="border-blue-200 bg-blue-50 dark:bg-blue-950 dark:border-blue-800">
        <AlertDescription className="text-sm text-blue-700 dark:text-blue-300">
          Enter your Databricks credentials to connect
        </AlertDescription>
      </Alert>

      {/* Token input */}
      <div className="space-y-1.5">
        <label className="text-sm font-medium flex items-center gap-1">
          Databricks API Token (PAT)
        </label>
        <div className="relative">
          <Input
            type={showToken ? "text" : "password"}
            placeholder="dapi..."
            value={token}
            onChange={(e) => handleTokenChange(e.target.value)}
            disabled={disabled}
            className="pr-10"
          />
          <button
            type="button"
            className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            onClick={() => setShowToken(!showToken)}
            tabIndex={-1}
          >
            {showToken ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        </div>
      </div>

      {/* Advanced Settings */}
      <button
        type="button"
        className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
        onClick={() => setShowAdvanced(!showAdvanced)}
      >
        {showAdvanced ? (
          <ChevronDown className="h-4 w-4" />
        ) : (
          <ChevronRight className="h-4 w-4" />
        )}
        Advanced Settings
      </button>

      {showAdvanced && (
        <Card className="border-dashed">
          <CardContent className="pt-4 grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">Host</label>
              <Input value={host} disabled className="text-xs" />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">HTTP Path</label>
              <Input value={httpPath} disabled className="text-xs" />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">Catalog</label>
              <Input value={catalog} disabled className="text-xs" />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">Schema</label>
              <Input value={schema} disabled className="text-xs" />
            </div>
          </CardContent>
        </Card>
      )}

      {/* Test Connection */}
      <Button
        variant="outline"
        size="sm"
        onClick={handleTestConnection}
        disabled={disabled || !token.trim() || connectionStatus === "testing"}
      >
        {connectionStatus === "testing" ? (
          <Loader2 className="h-4 w-4 mr-2 animate-spin" />
        ) : (
          <Zap className="h-4 w-4 mr-2" />
        )}
        Test Connection
      </Button>

      {/* Connection status banner */}
      {connectionStatus === "connected" && (
        <Alert className="border-green-300 bg-green-50 dark:bg-green-950 dark:border-green-800">
          <CheckCircle2 className="h-4 w-4 text-green-600" />
          <AlertDescription className="text-green-700 dark:text-green-300">
            {connectionMessage}
          </AlertDescription>
        </Alert>
      )}
      {connectionStatus === "error" && (
        <Alert className="border-red-300 bg-red-50 dark:bg-red-950 dark:border-red-800">
          <AlertCircle className="h-4 w-4 text-red-600" />
          <AlertDescription className="text-red-700 dark:text-red-300">
            {connectionMessage}
          </AlertDescription>
        </Alert>
      )}

      {/* Country filter */}
      {connectionStatus === "connected" && (
        <div className="space-y-1.5">
          <label className="text-sm font-medium">Filter by country (optional):</label>
          <select
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            value={countryFilter}
            onChange={(e) => setCountryFilter(e.target.value)}
            disabled={disabled}
          >
            <option value="all">All Countries</option>
            <option value="United States of America">United States of America</option>
            <option value="India">India</option>
            <option value="Germany">Germany</option>
            <option value="Oman">Oman</option>
          </select>
        </div>
      )}

      {/* Fetch Employee Data */}
      {connectionStatus === "connected" && (
        <Button
          onClick={handleFetchData}
          disabled={disabled || isFetching}
          className="w-full"
        >
          {isFetching ? (
            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
          ) : (
            <Database className="h-4 w-4 mr-2" />
          )}
          Fetch Employee Data
        </Button>
      )}

      {/* Fetch result */}
      {fetchedCount !== null && fetchedCount > 0 && (
        <Alert className="border-green-300 bg-green-50 dark:bg-green-950 dark:border-green-800">
          <CheckCircle2 className="h-4 w-4 text-green-600" />
          <AlertDescription className="text-green-700 dark:text-green-300">
            Loaded {fetchedCount.toLocaleString()} employee records from Databricks
          </AlertDescription>
        </Alert>
      )}
      {fetchedCount === -1 && (
        <Alert className="border-green-300 bg-green-50 dark:bg-green-950 dark:border-green-800">
          <CheckCircle2 className="h-4 w-4 text-green-600" />
          <AlertDescription className="text-green-700 dark:text-green-300">
            Databricks configured — employee data will be fetched when pipeline runs
          </AlertDescription>
        </Alert>
      )}
    </div>
  );
}
