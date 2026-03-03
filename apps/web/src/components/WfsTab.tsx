import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  cancelWfsJob,
  deleteWfsCollection,
  fetchWfsCollections,
  fetchWfsConfig,
  fetchWfsJob,
  fetchWfsLayers,
  startWfsCollection,
  updateWfsApiKey
} from "../api";
import { toErrorMessage } from "../error";
import { useAppStore } from "../store";
import type { WfsFilter } from "../types";
import { DataTable, formatMb, PaginationRow } from "./TableShell";
import { LoadingModal } from "./LoadingModal";
import { WfsBboxPicker } from "./WfsBboxPicker";

type WfsUiFilter = {
  type: "EQ" | "LIKE" | "BBOX";
  join_with_prev: "AND" | "OR";
  column: string;
  value: string;
  bbox?: [number, number, number, number];
  geom_column?: string;
};

function makeEmptyFilter(): WfsUiFilter {
  return { type: "LIKE", join_with_prev: "AND", column: "", value: "" };
}

export function WfsTab() {
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState("created_at");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [selectedLayerKey, setSelectedLayerKey] = useState("");
  const [outputFormat, setOutputFormat] = useState<"geoparquet" | "gpkg">("geoparquet");
  const [srsName, setSrsName] = useState("EPSG:5186");
  const [filterDraft, setFilterDraft] = useState<WfsUiFilter[]>([makeEmptyFilter()]);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [runningJobId, setRunningJobId] = useState<number | null>(null);
  const [isCancelling, setIsCancelling] = useState(false);
  const [isApiKeyModalOpen, setIsApiKeyModalOpen] = useState(false);
  const [isCollectModalOpen, setIsCollectModalOpen] = useState(false);

  const setActiveTab = useAppStore((s) => s.setActiveTab);
  const queryClient = useQueryClient();

  const configQuery = useQuery({ queryKey: ["wfs-config"], queryFn: fetchWfsConfig });
  const layersQuery = useQuery({ queryKey: ["wfs-layers"], queryFn: fetchWfsLayers });
  const collectionsQuery = useQuery({
    queryKey: ["wfs-collections", page, sortBy, sortDir],
    queryFn: () => fetchWfsCollections({ page, pageSize: 20, query: "", sortBy, sortDir })
  });

  const runningJobQuery = useQuery({
    queryKey: ["wfs-job", runningJobId],
    queryFn: () => fetchWfsJob(runningJobId as number),
    enabled: runningJobId !== null,
    refetchInterval: runningJobId !== null ? 1000 : false
  });

  const saveKeyMutation = useMutation({
    mutationFn: updateWfsApiKey,
    onSuccess: () => {
      setApiKeyInput("");
      setError("");
      setNotice("API 키를 저장했습니다.");
      setIsApiKeyModalOpen(false);
      queryClient.invalidateQueries({ queryKey: ["wfs-config"] });
    },
    onError: (err) => {
      setError(toErrorMessage(err, "API 키 저장 실패"));
    }
  });

  const startMutation = useMutation({
    mutationFn: startWfsCollection,
    onSuccess: (result) => {
      setRunningJobId(result.job_id);
      setError("");
      setNotice("WFS 수집 작업을 시작했습니다.");
      setIsCollectModalOpen(false);
    },
    onError: (err) => {
      setError(toErrorMessage(err, "WFS 수집 시작 실패"));
      setNotice("");
    }
  });

  const cancelMutation = useMutation({
    mutationFn: cancelWfsJob,
    onSuccess: () => {
      setIsCancelling(true);
      setError("");
      setNotice("중단 요청을 전송했습니다.");
    },
    onError: (err) => {
      setError(toErrorMessage(err, "중단 요청 실패"));
    }
  });

  const deleteMutation = useMutation({
    mutationFn: deleteWfsCollection,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["wfs-collections"] });
      queryClient.invalidateQueries({ queryKey: ["datasets"] });
    }
  });

  const layers = layersQuery.data ?? [];
  const hasApiKey = Boolean(configQuery.data?.has_api_key);
  const selectedLayer = useMemo(
    () => layers.find((item) => item.key === selectedLayerKey),
    [layers, selectedLayerKey]
  );
  const bboxFilterIndex = useMemo(
    () => filterDraft.findIndex((item) => item.type === "BBOX"),
    [filterDraft]
  );
  const bboxFilter = bboxFilterIndex >= 0 ? filterDraft[bboxFilterIndex] : null;

  useEffect(() => {
    if (!layers.length) {
      if (selectedLayerKey) {
        setSelectedLayerKey("");
      }
      return;
    }
    if (selectedLayerKey && !layers.some((item) => item.key === selectedLayerKey)) {
      setSelectedLayerKey("");
    }
  }, [layers, selectedLayerKey]);

  useEffect(() => {
    if (!runningJobId || !runningJobQuery.data) {
      return;
    }
    const status = runningJobQuery.data.status;
    if (status === "queued" || status === "running") {
      return;
    }
    setIsCancelling(false);
    setRunningJobId(null);

    if (status === "succeeded") {
      setError("");
      setNotice("WFS 수집이 완료되었습니다. Browse & Map에서 결과를 확인하세요.");
      queryClient.invalidateQueries({ queryKey: ["wfs-collections"] });
      queryClient.invalidateQueries({ queryKey: ["datasets"] });
      return;
    }
    if (status === "cancelled") {
      setError("");
      setNotice("WFS 수집이 중단되었습니다.");
      return;
    }
    setNotice("");
    setError(runningJobQuery.data.error_message?.trim() || "WFS 수집 실패");
  }, [runningJobId, runningJobQuery.data, queryClient]);

  const rows = useMemo(() => {
    const items = collectionsQuery.data?.items ?? [];
    return items.map((item) => ({
      action: (
        <button
          className="icon-btn danger"
          onClick={() => deleteMutation.mutate(item.file_id)}
          aria-label="삭제"
          title="삭제"
        >
          🗑️
        </button>
      ),
      id: item.id,
      name: <strong>{item.name}</strong>,
      size: formatMb(item.size_bytes),
      rows: (item.total_rows ?? 0).toLocaleString(),
      crs: item.crs || "-",
      filters: (
        <span className="wfs-filter-cell" title={item.filter_detail_text || item.filter_summary || "필터 없음"}>
          {item.filter_summary || "전체"}
        </span>
      ),
      created: item.created_at,
      path: item.path
    }));
  }, [collectionsQuery.data?.items, deleteMutation]);

  const openCollectModal = () => {
    if (!selectedLayer) {
      setError("먼저 좌측 레이어 목록에서 대상을 선택해 주세요.");
      return;
    }
    if (!hasApiKey) {
      setIsApiKeyModalOpen(true);
      return;
    }
    setError("");
    setFilterDraft([makeEmptyFilter()]);
    setIsCollectModalOpen(true);
  };

  const onSortChange = (nextSortBy: string) => {
    setPage(1);
    if (sortBy === nextSortBy) {
      setSortDir((prev) => (prev === "asc" ? "desc" : "asc"));
      return;
    }
    setSortBy(nextSortBy);
    setSortDir(nextSortBy === "created_at" ? "desc" : "asc");
  };

  const runCollection = () => {
    if (!selectedLayer) {
      setError("레이어를 선택해 주세요.");
      return;
    }
    if (!hasApiKey) {
      setIsApiKeyModalOpen(true);
      return;
    }

    const bboxFilterCount = filterDraft.filter((item) => item.type === "BBOX").length;
    if (bboxFilterCount > 1) {
      setError("BBOX 필터는 1개만 사용할 수 있습니다.");
      return;
    }

    const normalizedFilters: WfsFilter[] = [];
    for (let i = 0; i < filterDraft.length; i += 1) {
      const current = filterDraft[i];
      if (current.type === "BBOX") {
        if (!current.bbox || current.bbox.length !== 4) {
          setError("BBOX 필터의 영역을 먼저 선택해 주세요. (Shift/Ctrl + 드래그)");
          return;
        }
        normalizedFilters.push({
          type: "BBOX",
          bbox: current.bbox,
          geom_column: current.geom_column || "ag_geom",
          join_with_prev: i === 0 ? undefined : current.join_with_prev
        });
        continue;
      }
      const column = current.column.trim();
      const value = current.value.trim();
      if (!column && !value) {
        continue;
      }
      if (!column || !value) {
        setError(`필터 ${i + 1}의 컬럼과 값을 모두 입력해 주세요.`);
        return;
      }
      const normalizedType =
        current.type === "EQ" && (value.includes("*") || value.includes("?")) ? "LIKE" : current.type;
      normalizedFilters.push({
        type: normalizedType,
        column,
        value,
        join_with_prev: i === 0 ? undefined : current.join_with_prev
      });
    }

    setError("");
    startMutation.mutate({
      layer_key: selectedLayer.key,
      output_format: outputFormat,
      srs_name: srsName,
      filters: normalizedFilters.length ? normalizedFilters : undefined,
      bbox_split: 1
    });
  };

  return (
    <section className="tab-section">
      <LoadingModal
        open={startMutation.isPending || runningJobId !== null}
        title="WFS 수집 중..."
        progressPercent={
          typeof runningJobQuery.data?.progress_percent === "number"
            ? runningJobQuery.data.progress_percent
            : startMutation.isPending
              ? 5
              : undefined
        }
        progressLabel={runningJobQuery.data?.progress_message || (startMutation.isPending ? "작업을 준비하는 중입니다." : undefined)}
        description={
          isCancelling
            ? "중단 요청을 처리하고 있습니다. 현재 단계를 마친 뒤 중단됩니다."
            : "WFS 데이터를 조회하고 파일로 저장하는 중입니다."
        }
        cancelLabel={isCancelling ? "중단 요청 중..." : "중단"}
        cancelDisabled={isCancelling || cancelMutation.isPending}
        onCancel={
          runningJobId !== null
            ? () => {
                if (!isCancelling) {
                  cancelMutation.mutate(runningJobId);
                }
              }
            : undefined
        }
      />

      {isApiKeyModalOpen && (
        <div className="dialog-backdrop" onClick={() => setIsApiKeyModalOpen(false)}>
          <div className="dialog-card wfs-key-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="dialog-head">
              <h4>VWorld API 키 설정</h4>
              <button className="icon-btn" onClick={() => setIsApiKeyModalOpen(false)} aria-label="닫기">
                ✕
              </button>
            </div>
            <p className="section-help">API 키가 없으면 WFS 수집을 시작할 수 없습니다.</p>
            <label className="input-group">
              <span>API 키</span>
              <input
                type="password"
                placeholder="VWorld API 키 입력"
                value={apiKeyInput}
                onChange={(e) => setApiKeyInput(e.target.value)}
              />
              <small className="hint-text">현재 상태: {hasApiKey ? `저장됨 (${configQuery.data?.key_masked})` : "미설정"}</small>
            </label>
            <div className="dialog-actions">
              <button className="ghost" onClick={() => setIsApiKeyModalOpen(false)}>
                닫기
              </button>
              <button
                className="primary"
                onClick={() => saveKeyMutation.mutate(apiKeyInput)}
                disabled={!apiKeyInput.trim() || saveKeyMutation.isPending}
              >
                {saveKeyMutation.isPending ? "저장 중..." : "저장"}
              </button>
            </div>
          </div>
        </div>
      )}

      {isCollectModalOpen && selectedLayer && (
        <div className="dialog-backdrop" onClick={() => setIsCollectModalOpen(false)}>
          <div className="dialog-card wfs-collect-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="dialog-head wfs-collect-head">
              <h4>WFS 수집 조건 설정</h4>
              <button className="icon-btn" onClick={() => setIsCollectModalOpen(false)} aria-label="닫기">
                ✕
              </button>
            </div>
            <div className="wfs-modal-summary">
              <strong>{selectedLayer.display_name}</strong>
              <span>{selectedLayer.typename}</span>
            </div>
            <div className="row grid-3">
              <label className="input-group">
                <span>출력 형식</span>
                <select value={outputFormat} onChange={(e) => setOutputFormat(e.target.value as "geoparquet" | "gpkg")}>
                  <option value="geoparquet">geoparquet</option>
                  <option value="gpkg">gpkg</option>
                </select>
              </label>
              <label className="input-group">
                <span>SRSNAME</span>
                <input value={srsName} onChange={(e) => setSrsName(e.target.value)} />
              </label>
              <div className="wfs-modal-note">
                조건이 없으면 선택 레이어 전체를 수집합니다.
              </div>
            </div>

            <div className="wfs-filter-list modal">
              {filterDraft.map((filter, index) => (
                <div key={`collect-filter-${index}`} className="wfs-filter-item">
                  {index === 0 ? (
                    <div className="wfs-filter-anchor">조건 1</div>
                  ) : (
                    <select
                      value={filter.join_with_prev}
                      onChange={(e) => {
                        const next = [...filterDraft];
                        next[index] = { ...next[index], join_with_prev: e.target.value as "AND" | "OR" };
                        setFilterDraft(next);
                      }}
                    >
                      <option value="AND">AND</option>
                      <option value="OR">OR</option>
                    </select>
                  )}

                  <select
                    value={filter.type}
                    onChange={(e) => {
                      const nextType = e.target.value as "EQ" | "LIKE" | "BBOX";
                      if (nextType === "BBOX" && filterDraft.some((item, idx) => idx !== index && item.type === "BBOX")) {
                        setError("BBOX 필터는 1개만 사용할 수 있습니다.");
                        return;
                      }
                      const next = [...filterDraft];
                      next[index] = {
                        ...next[index],
                        type: nextType,
                        column: nextType === "BBOX" ? "" : next[index].column,
                        value: nextType === "BBOX" ? "" : next[index].value,
                        bbox: nextType === "BBOX" ? next[index].bbox : undefined,
                        geom_column: nextType === "BBOX" ? next[index].geom_column || "ag_geom" : undefined
                      };
                      setFilterDraft(next);
                      setError("");
                    }}
                  >
                    <option value="EQ">EQ</option>
                    <option value="LIKE">LIKE</option>
                    <option value="BBOX">BBOX</option>
                  </select>

                  {filter.type === "BBOX" ? (
                    <div className="wfs-filter-bbox-summary" style={{ gridColumn: "span 2" }}>
                      {filter.bbox ? (
                        <code>{filter.bbox.map((value) => value.toFixed(6)).join(", ")}</code>
                      ) : (
                        <span>Shift 또는 Ctrl 키를 누른 채 지도에서 드래그해 영역을 선택하세요.</span>
                      )}
                    </div>
                  ) : (
                    <>
                      <select
                        value={filter.column}
                        onChange={(e) => {
                          const next = [...filterDraft];
                          next[index] = { ...next[index], column: e.target.value };
                          setFilterDraft(next);
                        }}
                      >
                        <option value="">컬럼 선택</option>
                        {selectedLayer.columns.map((column) => (
                          <option key={`column-${column.name}`} value={column.name}>
                            {column.name} ({column.name_ko})
                          </option>
                        ))}
                      </select>

                      <input
                        placeholder={filter.type === "LIKE" ? "값 (예: 41*)" : "값"}
                        value={filter.value}
                        onChange={(e) => {
                          const next = [...filterDraft];
                          next[index] = { ...next[index], value: e.target.value };
                          setFilterDraft(next);
                        }}
                      />
                    </>
                  )}

                  <button
                    className="ghost compact"
                    onClick={() => {
                      if (filter.type === "BBOX" && filter.bbox) {
                        setFilterDraft((prev) =>
                          prev.map((item, idx) => (idx === index ? { ...item, bbox: undefined } : item))
                        );
                        return;
                      }
                      setFilterDraft((prev) => {
                        const next = prev.filter((_, idx) => idx !== index);
                        return next.length > 0 ? next : [makeEmptyFilter()];
                      });
                    }}
                    disabled={filterDraft.length <= 1 && !(filter.type === "BBOX" && filter.bbox)}
                  >
                    {filter.type === "BBOX" && filter.bbox ? "초기화" : "삭제"}
                  </button>
                </div>
              ))}
            </div>

            {bboxFilter && (
              <div className="wfs-bbox-editor">
                <div className="wfs-bbox-editor-head">
                  <strong>BBOX 영역 선택</strong>
                  <span>지도 이동/확대/축소는 자유롭고, 영역 선택은 Shift/Ctrl + 드래그로 동작합니다.</span>
                </div>
                <WfsBboxPicker
                  value={bboxFilter.bbox ?? null}
                  onChange={(nextBbox) => {
                    setFilterDraft((prev) =>
                      prev.map((item, idx) =>
                        idx === bboxFilterIndex ? { ...item, bbox: nextBbox, geom_column: item.geom_column || "ag_geom" } : item
                      )
                    );
                    setError("");
                  }}
                />
              </div>
            )}

            <div className="dialog-actions left">
              <button className="ghost compact" onClick={() => setFilterDraft((prev) => [...prev, makeEmptyFilter()])}>
                + 조건 추가
              </button>
            </div>
            <div className="dialog-actions">
              <button className="ghost" onClick={() => setIsCollectModalOpen(false)}>
                취소
              </button>
              <button className="primary" onClick={runCollection} disabled={startMutation.isPending || runningJobId !== null}>
                수집 시작
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="panel">
        <h3>WFS 수집</h3>
        <p className="section-help">레이어를 선택한 뒤 수집 버튼에서 필터 조건(EQ/LIKE, AND/OR)을 설정합니다.</p>

        <div className={hasApiKey ? "wfs-inline-alert ok" : "wfs-inline-alert"}>
          <span>{hasApiKey ? `API 키 설정됨 (${configQuery.data?.key_masked})` : "API 키가 설정되지 않았습니다."}</span>
          <button className="ghost compact" onClick={() => setIsApiKeyModalOpen(true)}>
            {hasApiKey ? "키 변경" : "키 등록"}
          </button>
        </div>

        <div className="row wfs-toolbar">
          <button className="primary wfs-run-button" onClick={openCollectModal} disabled={!selectedLayer || runningJobId !== null}>
            수집 조건 설정
          </button>
        </div>

        {notice && (
          <p className="info">
            {notice}{" "}
            {notice.includes("Browse") && (
              <button className="ghost compact" onClick={() => setActiveTab("browse")}>
                Browse로 이동
              </button>
            )}
          </p>
        )}
        {error && <p className="error">{error}</p>}
      </div>

      <div className="panel">
        <h3>호출 가능 레이어</h3>
        <div className="wfs-browser-grid">
          <div className="wfs-layer-list">
            {layers.map((layer) => (
              <button
                key={layer.key}
                className={layer.key === selectedLayerKey ? "wfs-layer-item active" : "wfs-layer-item"}
                onClick={() => setSelectedLayerKey(layer.key)}
              >
                <strong>{layer.display_name}</strong>
                <span>{layer.typename}</span>
              </button>
            ))}
          </div>
          <div className="wfs-column-panel">
            {selectedLayer ? (
              <>
                <div className="wfs-column-head">
                  <strong>{selectedLayer.display_name}</strong>
                  <span>{selectedLayer.columns.length}개 컬럼</span>
                </div>
                <div className="preview-table-wrap">
                  <table className="preview-table">
                    <thead>
                      <tr>
                        <th>영문 컬럼명</th>
                        <th>한글 컬럼명</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selectedLayer.columns.map((column) => (
                        <tr key={`col-${column.name}`}>
                          <td>{column.name}</td>
                          <td>{column.name_ko}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            ) : (
              <div className="preview-empty">좌측 레이어를 선택하면 컬럼 메타가 표시됩니다.</div>
            )}
          </div>
        </div>
      </div>

      <div className="panel">
        <h3>WFS 수집 결과</h3>
        <p className="section-help">수집된 파일은 Browse & Map에서 동일하게 미리보기/시각화할 수 있습니다.</p>
        <DataTable
          columns={[
            { key: "action", title: "관리", width: "84px", align: "center" },
            { key: "id", title: "번호", width: "76px", sortable: true, sortKey: "id" },
            { key: "name", title: "레이어", width: "220px", sortable: true, sortKey: "name" },
            { key: "size", title: "저장 용량", width: "140px", sortable: true, sortKey: "size_bytes" },
            { key: "rows", title: "행수", width: "100px", sortable: true, sortKey: "total_rows", align: "right" },
            { key: "crs", title: "좌표계", width: "130px", sortable: true, sortKey: "crs" },
            { key: "filters", title: "필터 조건", width: "320px", sortable: true, sortKey: "filter_summary" },
            { key: "created", title: "생성 시각", width: "196px", sortable: true, sortKey: "created_at" },
            { key: "path", title: "경로", sortable: true, sortKey: "path" }
          ]}
          rows={rows}
          emptyText="WFS 수집 결과가 없습니다."
          sortBy={sortBy}
          sortDir={sortDir}
          onSortChange={onSortChange}
        />
        <PaginationRow
          page={page}
          totalPages={collectionsQuery.data?.total_pages ?? 1}
          totalItems={collectionsQuery.data?.total_items ?? 0}
          onPrev={() => setPage((p) => Math.max(1, p - 1))}
          onNext={() => setPage((p) => Math.min(collectionsQuery.data?.total_pages ?? 1, p + 1))}
        />
      </div>
    </section>
  );
}
