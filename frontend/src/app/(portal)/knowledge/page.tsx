"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { PanelGroup, Panel, PanelResizeHandle, ImperativePanelHandle } from "react-resizable-panels";
import { api } from "@/lib/api";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { KnowledgeTable } from "@/components/knowledge/knowledge-table";
import { KnowledgeFilters } from "@/components/knowledge/knowledge-filters";
import { UploadDialog } from "@/components/knowledge/upload-dialog";
import { KnowledgeTypeCards } from "@/components/types/knowledge-type-cards";
import { KnowledgeTypeDialog } from "@/components/types/knowledge-type-dialog";

export type KnowledgeType = {
  id: string;
  slug: string;
  name: string;
  color: string;
  description?: string;
  sort_order: number;
  source_count?: number;
};

export type Department = {
  id: string;
  name: string;
};

export type Source = {
  id: string;
  title: string;
  file_name?: string;
  source_type?: string;
  status: string;
  progress?: number;
  progress_message?: string;
  page_count?: number;
  wiki_page_count?: number;
  knowledge_type_id?: string;
  knowledge_type_name?: string;
  knowledge_type_color?: string;
  department_ids?: string[];
  department_names?: string[];
  contributed_by_name?: string;
  scope_type?: string;
  scope_id?: string;
  created_at: string;
  updated_at?: string;
};

type PaginatedSources = {
  items: Source[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

export default function KnowledgePage() {
  const [activeTab, setActiveTab] = useState("documents");

  // Resizable filter panel (size + collapse persisted via PanelGroup autoSaveId).
  const leftPanelRef = useRef<ImperativePanelHandle>(null);
  const [filtersCollapsed, setFiltersCollapsed] = useState(false);

  const [sources, setSources] = useState<Source[]>([]);
  const [types, setTypes] = useState<KnowledgeType[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [selectedType, setSelectedType] = useState<string | null>(null);
  const [selectedDepartment, setSelectedDepartment] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState("");
  const pageSize = 20;
  
  const [typeDialogOpen, setTypeDialogOpen] = useState(false);
  const [editType, setEditType] = useState<KnowledgeType | null>(null);

  const loadSources = useCallback(async (silent = false, p = 1, s = "") => {
    if (!silent) setLoading(true);
    try {
      const params = new URLSearchParams({
        page: String(p),
        page_size: String(pageSize),
      });
      if (selectedType) {
        const matchedType = types.find((t) => t.slug === selectedType);
        if (matchedType) params.set("knowledge_type_id", matchedType.id);
      }
      if (selectedDepartment) params.set("department_id", selectedDepartment);
      if (s) params.set("search", s);

      const data = await api<PaginatedSources>(`/api/sources?${params}`);
      setSources(data.items);
      setTotal(data.total);
      setTotalPages(data.total_pages);
      setPage(data.page);
    } catch {
      if (!silent) setSources([]);
    } finally {
      if (!silent) setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedType, selectedDepartment, types]);

  // Polling cho trạng thái tài liệu
  useEffect(() => {
    const hasPending = sources.some((s) => s.status === "pending" || s.status === "processing" || s.status === "plan_ready");
    if (!hasPending) return;

    const interval = setInterval(() => {
      loadSources(true, page, search);
    }, 3000);

    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sources, loadSources]);

  const loadMeta = useCallback(async () => {
    try {
      const [typesData, deptsData] = await Promise.all([
        api<KnowledgeType[]>("/api/knowledge-types"),
        api<Department[]>("/api/departments"),
      ]);
      setTypes(typesData);
      setDepartments(deptsData);
    } catch {
      setTypes([]);
      setDepartments([]);
    }
  }, []);

  useEffect(() => {
    loadMeta();
  }, [loadMeta]);

  useEffect(() => {
    loadSources();
  }, [loadSources]);

  const handleSearch = (q: string) => {
    setSearch(q);
    setPage(1);
    loadSources(false, 1, q);
  };

  const handlePageChange = (p: number) => {
    setPage(p);
    loadSources(false, p, search);
  };

  return (
    <>
      <PageHeader
        title="Knowledge Base"
        description="Manage and organize your organization's documents and categories."
        action={
          activeTab === "documents" ? (
            <Button
              onClick={() => setUploadOpen(true)}
              className="bg-primary text-primary-foreground hover:bg-primary/90"
            >
              <span className="material-symbols-outlined text-base mr-1">add</span>
              Upload Document
            </Button>
          ) : (
            <Button
              onClick={() => { setEditType(null); setTypeDialogOpen(true); }}
              className="bg-primary text-primary-foreground hover:bg-primary/90"
            >
              <span className="material-symbols-outlined text-base mr-1">add</span>
              Add Category
            </Button>
          )
        }
      />

      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full flex-1 min-h-0">
        <TabsList className="mb-6">
          <TabsTrigger value="documents" className="gap-2">
            <span className="material-symbols-outlined text-[18px]">files</span>
            Documents
          </TabsTrigger>
          <TabsTrigger value="types" className="gap-2">
            <span className="material-symbols-outlined text-[18px]">category</span>
            Categories
          </TabsTrigger>
        </TabsList>

        <TabsContent value="documents" className="mt-0 outline-none flex-1 min-h-0 flex flex-col">
          <div className="flex-1 flex min-h-0 overflow-hidden">
            <PanelGroup direction="horizontal" autoSaveId="knowledge-docs-panels" className="flex-1">
              <Panel
                id="filters"
                ref={leftPanelRef}
                order={1}
                collapsible
                collapsedSize={3}
                minSize={14}
                maxSize={32}
                defaultSize={22}
                onCollapse={() => setFiltersCollapsed(true)}
                onExpand={() => setFiltersCollapsed(false)}
                className="min-w-0"
              >
                {filtersCollapsed ? (
                  <div className="h-full w-full border-r border-border bg-card/30 flex flex-col items-center pt-4 gap-3">
                    <button
                      onClick={() => leftPanelRef.current?.expand()}
                      title="Expand filters"
                      className="text-muted-foreground hover:text-foreground transition-colors"
                    >
                      <span className="material-symbols-outlined text-base">left_panel_open</span>
                    </button>
                    <span className="material-symbols-outlined text-base text-muted-foreground">filter_list</span>
                  </div>
                ) : (
                  <div className="h-full w-full flex flex-col overflow-hidden border-r border-border">
                    <div className="flex items-center gap-2 px-3 py-2 shrink-0">
                      <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex-1">
                        Filters
                      </span>
                      <button
                        onClick={() => leftPanelRef.current?.collapse()}
                        title="Collapse"
                        className="text-muted-foreground hover:text-foreground transition-colors"
                      >
                        <span className="material-symbols-outlined text-base">left_panel_close</span>
                      </button>
                    </div>
                    <div className="flex-1 overflow-y-auto pr-3 pb-4">
                      <KnowledgeFilters
                        types={types}
                        selectedType={selectedType}
                        onSelectType={setSelectedType}
                        departments={departments}
                        selectedDepartment={selectedDepartment}
                        onSelectDepartment={setSelectedDepartment}
                      />
                    </div>
                  </div>
                )}
              </Panel>

              <PanelResizeHandle className="group relative flex w-2 shrink-0 items-stretch justify-center bg-transparent outline-none cursor-col-resize">
                <div className="w-px bg-border transition-colors group-hover:bg-primary/60 group-data-[resize-handle-state=drag]:bg-primary" />
              </PanelResizeHandle>

              <Panel id="table" order={2} minSize={40} className="min-w-0">
                <div className="h-full overflow-y-auto pl-4">
                  <KnowledgeTable
                    sources={sources}
                    types={types}
                    departments={departments}
                    loading={loading}
                    onRefresh={() => loadSources(false, page, search)}
                    page={page}
                    totalPages={totalPages}
                    total={total}
                    onPageChange={handlePageChange}
                    search={search}
                    onSearch={handleSearch}
                  />
                </div>
              </Panel>
            </PanelGroup>
          </div>
        </TabsContent>

        <TabsContent value="types" className="mt-0 outline-none flex-1 min-h-0 overflow-y-auto">
          <KnowledgeTypeCards
            types={types}
            loading={types.length === 0 && loading}
            onEdit={(t) => { setEditType(t); setTypeDialogOpen(true); }}
            onRefresh={loadMeta}
          />
        </TabsContent>
      </Tabs>

      <UploadDialog
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        types={types}
        departments={departments}
        onUploaded={() => loadSources(false, page, search)}
      />

      <KnowledgeTypeDialog
        open={typeDialogOpen}
        onOpenChange={setTypeDialogOpen}
        knowledgeType={editType}
        onSaved={loadMeta}
      />
    </>
  );
}
