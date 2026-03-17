'use client';

import { useState } from 'react';
import { formatDistanceToNow } from 'date-fns';
import { Search, ChevronLeft, ChevronRight, FileText, Loader2 } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { Skeleton } from '@/components/ui/skeleton';
import { useIncidents, useAdapters, useGenerateReport } from '@/hooks/useNightwatch';
import { cn } from '@/lib/utils';

type Incident = {
  id: string;
  severity: string;
  component: string;
  message: string;
  adapter: string;
  started_at: string;
  resolved_at?: string | null;
  status: string;
  ai_analysis?: string;
};

function severityBg(sev: string) {
  switch (sev) {
    case 'P1': return 'bg-red-500/10 text-red-400 border-red-500/20';
    case 'P2': return 'bg-orange-500/10 text-orange-400 border-orange-500/20';
    case 'P3': return 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20';
    default: return 'bg-slate-500/10 text-slate-400 border-slate-500/20';
  }
}

function duration(started: string, resolved?: string | null) {
  const end = resolved ? new Date(resolved) : new Date();
  const ms = end.getTime() - new Date(started).getTime();
  const minutes = Math.floor(ms / 60000);
  if (minutes < 60) return `${minutes}m`;
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

const PAGE_SIZE = 15;

export default function IncidentsPage() {
  const [search, setSearch] = useState('');
  const [severity, setSeverity] = useState('all');
  const [adapterFilter, setAdapterFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Incident | null>(null);

  const { data: incidents, isLoading } = useIncidents({ limit: 100 });
  const { data: adapters } = useAdapters();
  const { mutate: generateReport, isPending: generatingReport, data: reportData } = useGenerateReport();

  const adapterNames = adapters?.adapters?.map((a: { name: string }) => a.name) ?? [];

  const filtered = (incidents?.incidents ?? []).filter((inc: Incident) => {
    const matchSearch =
      !search ||
      inc.component.toLowerCase().includes(search.toLowerCase()) ||
      inc.message.toLowerCase().includes(search.toLowerCase()) ||
      inc.id.toLowerCase().includes(search.toLowerCase());
    const matchSev = severity === 'all' || inc.severity === severity;
    const matchAdapter = adapterFilter === 'all' || inc.adapter === adapterFilter;
    const matchStatus = statusFilter === 'all' || inc.status === statusFilter;
    return matchSearch && matchSev && matchAdapter && matchStatus;
  });

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const paginated = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  return (
    <div className="p-6 lg:pt-6 pt-16 space-y-4">
      <div>
        <h1 className="text-xl font-bold text-slate-100">Incidents</h1>
        <p className="text-sm text-slate-500">{incidents?.total ?? 0} total incidents</p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 items-center">
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
          <Input
            placeholder="Search incidents…"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
            className="pl-9 bg-slate-900 border-slate-700 text-slate-100 placeholder:text-slate-500 focus:border-indigo-500"
          />
        </div>

        <Select value={severity} onValueChange={(v) => { setSeverity(v ?? "all"); setPage(1); }}>
          <SelectTrigger className="w-[120px] bg-slate-900 border-slate-700 text-slate-300">
            <SelectValue placeholder="Severity" />
          </SelectTrigger>
          <SelectContent className="bg-slate-900 border-slate-700">
            <SelectItem value="all">All Severity</SelectItem>
            <SelectItem value="P1">P1 Critical</SelectItem>
            <SelectItem value="P2">P2 Warning</SelectItem>
            <SelectItem value="P3">P3 Info</SelectItem>
          </SelectContent>
        </Select>

        <Select value={adapterFilter} onValueChange={(v) => { setAdapterFilter(v ?? "all"); setPage(1); }}>
          <SelectTrigger className="w-[140px] bg-slate-900 border-slate-700 text-slate-300">
            <SelectValue placeholder="Adapter" />
          </SelectTrigger>
          <SelectContent className="bg-slate-900 border-slate-700">
            <SelectItem value="all">All Adapters</SelectItem>
            {adapterNames.map((name: string) => (
              <SelectItem key={name} value={name}>{name}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={statusFilter} onValueChange={(v) => { setStatusFilter(v ?? "all"); setPage(1); }}>
          <SelectTrigger className="w-[130px] bg-slate-900 border-slate-700 text-slate-300">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent className="bg-slate-900 border-slate-700">
            <SelectItem value="all">All Status</SelectItem>
            <SelectItem value="active">Active</SelectItem>
            <SelectItem value="resolved">Resolved</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Table */}
      <Card className="bg-slate-900 border-slate-800">
        {isLoading ? (
          <CardContent className="p-4 space-y-3">
            {[...Array(5)].map((_, i) => (
              <Skeleton key={i} className="h-12 w-full bg-slate-800" />
            ))}
          </CardContent>
        ) : paginated.length === 0 ? (
          <CardContent className="p-10 text-center text-slate-500 text-sm">
            No incidents match your filters
          </CardContent>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-800">
                  <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase">ID</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase">Severity</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase">Component</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase">Message</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase">Adapter</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase">Started</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase">Duration</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase">Status</th>
                </tr>
              </thead>
              <tbody>
                {paginated.map((inc: Incident) => (
                  <tr
                    key={inc.id}
                    onClick={() => setSelected(inc)}
                    className="border-b border-slate-800 hover:bg-slate-800/40 cursor-pointer transition-colors"
                  >
                    <td className="px-4 py-3 text-xs text-slate-500 font-mono">{inc.id}</td>
                    <td className="px-4 py-3">
                      <Badge variant="outline" className={cn('text-xs font-bold', severityBg(inc.severity))}>
                        {inc.severity}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 text-sm text-slate-300 font-medium">{inc.component}</td>
                    <td className="px-4 py-3 text-sm text-slate-400 max-w-xs">
                      <span className="line-clamp-1">{inc.message}</span>
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-500">{inc.adapter}</td>
                    <td className="px-4 py-3 text-xs text-slate-500">
                      {formatDistanceToNow(new Date(inc.started_at), { addSuffix: true })}
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-500">
                      {duration(inc.started_at, inc.resolved_at)}
                    </td>
                    <td className="px-4 py-3">
                      <Badge
                        variant="outline"
                        className={cn('text-xs', inc.status === 'active'
                          ? 'bg-red-500/10 text-red-400 border-red-500/20'
                          : 'bg-green-500/10 text-green-400 border-green-500/20'
                        )}
                      >
                        {inc.status}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm text-slate-500">
          <span>
            Showing {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, filtered.length)} of {filtered.length}
          </span>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page === 1}
              className="border-slate-700 text-slate-400 hover:bg-slate-800"
            >
              <ChevronLeft className="w-4 h-4" />
            </Button>
            <span className="text-slate-400 px-2">{page} / {totalPages}</span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="border-slate-700 text-slate-400 hover:bg-slate-800"
            >
              <ChevronRight className="w-4 h-4" />
            </Button>
          </div>
        </div>
      )}

      {/* Incident Detail Sheet */}
      <Sheet open={!!selected} onOpenChange={() => setSelected(null)}>
        <SheetContent className="bg-slate-900 border-slate-800 text-slate-100 w-full sm:max-w-xl overflow-y-auto">
          <SheetHeader className="pb-4 border-b border-slate-800">
            <SheetTitle className="flex items-center gap-2 text-slate-100">
              {selected && (
                <Badge variant="outline" className={cn('text-xs font-bold', severityBg(selected.severity))}>
                  {selected.severity}
                </Badge>
              )}
              Incident Details
            </SheetTitle>
          </SheetHeader>

          {selected && (
            <div className="py-4 space-y-5">
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="text-slate-500 text-xs mb-1">ID</p>
                  <p className="text-slate-300 font-mono text-xs">{selected.id}</p>
                </div>
                <div>
                  <p className="text-slate-500 text-xs mb-1">Status</p>
                  <Badge variant="outline" className={cn('text-xs', selected.status === 'active' ? 'bg-red-500/10 text-red-400 border-red-500/20' : 'bg-green-500/10 text-green-400 border-green-500/20')}>
                    {selected.status}
                  </Badge>
                </div>
                <div>
                  <p className="text-slate-500 text-xs mb-1">Component</p>
                  <p className="text-slate-200 font-medium">{selected.component}</p>
                </div>
                <div>
                  <p className="text-slate-500 text-xs mb-1">Adapter</p>
                  <p className="text-slate-200">{selected.adapter}</p>
                </div>
                <div>
                  <p className="text-slate-500 text-xs mb-1">Started</p>
                  <p className="text-slate-300">{new Date(selected.started_at).toLocaleString()}</p>
                </div>
                <div>
                  <p className="text-slate-500 text-xs mb-1">Duration</p>
                  <p className="text-slate-300">{duration(selected.started_at, selected.resolved_at)}</p>
                </div>
              </div>

              <div>
                <p className="text-slate-500 text-xs mb-2">Message</p>
                <div className="bg-slate-800 rounded-lg p-3 text-sm text-slate-200 leading-relaxed">
                  {selected.message}
                </div>
              </div>

              {selected.ai_analysis && (
                <div>
                  <p className="text-slate-500 text-xs mb-2 flex items-center gap-1">
                    ⚡ AI Root Cause Analysis
                  </p>
                  <div className="bg-indigo-950/40 border border-indigo-500/20 rounded-lg p-3 text-sm text-slate-300 leading-relaxed">
                    {selected.ai_analysis}
                  </div>
                </div>
              )}

              {/* Timeline */}
              <div>
                <p className="text-slate-500 text-xs mb-2">Timeline</p>
                <div className="space-y-2">
                  <div className="flex items-start gap-3 text-xs">
                    <div className="w-2 h-2 rounded-full bg-red-400 mt-1 flex-shrink-0" />
                    <div>
                      <span className="text-slate-400 font-medium">Incident started</span>
                      <p className="text-slate-500">{new Date(selected.started_at).toLocaleString()}</p>
                    </div>
                  </div>
                  {selected.resolved_at && (
                    <div className="flex items-start gap-3 text-xs">
                      <div className="w-2 h-2 rounded-full bg-green-400 mt-1 flex-shrink-0" />
                      <div>
                        <span className="text-slate-400 font-medium">Incident resolved</span>
                        <p className="text-slate-500">{new Date(selected.resolved_at).toLocaleString()}</p>
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* Generate Report */}
              <div className="border-t border-slate-800 pt-4">
                <Button
                  onClick={() => generateReport({ incident_id: selected.id, adapter: selected.adapter })}
                  disabled={generatingReport}
                  className="w-full bg-indigo-600 hover:bg-indigo-700 text-white"
                >
                  {generatingReport ? (
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  ) : (
                    <FileText className="w-4 h-4 mr-2" />
                  )}
                  Generate AI Report
                </Button>

                {reportData?.report && (
                  <div className="mt-4 bg-slate-800 rounded-lg p-4 text-xs text-slate-300 whitespace-pre-wrap font-mono overflow-y-auto max-h-64">
                    {reportData.report}
                  </div>
                )}
              </div>
            </div>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}
