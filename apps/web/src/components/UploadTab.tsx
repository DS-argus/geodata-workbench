import { useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createUploads, deleteUpload, inspectTabularUpload, submitTabularUpload, fetchUploads } from "../api";
import { toErrorMessage } from "../error";
import { LoadingModal } from "./LoadingModal";
import { DeleteConfirmDialog } from "./DeleteSafety";
import { DataTable, formatMb, PaginationRow } from "./TableShell";
import { useModalA11y } from "./useModalA11y";

type TabularPreview = {
  columns: string[];
  sample_rows: Record<string, unknown>[];
  numeric_ranges: Record<string, { min: number; max: number; count: number }>;
  suggested_lat?: string | null;
  suggested_lon?: string | null;
  lat_reference: { min: number; max: number };
  lon_reference: { min: number; max: number };
};

type ErrorModalState = {
  open: boolean;
  title: string;
  message: string;
  details?: string[];
};

function fileExtension(name: string): string {
  const idx = name.lastIndexOf(".");
  return idx >= 0 ? name.slice(idx + 1).toLowerCase() : "";
}

function trimFileNameToSeconds(name: string): string {
  if (!name) return "";
  return name.replace(/_(\d{8}_\d{6})_\d+(?=\.[^.]+$)/, "_$1");
}

export function UploadTab() {
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState("created_at");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [outputFormat, setOutputFormat] = useState<"geoparquet" | "gpkg">("geoparquet");
  const [uploadNotice, setUploadNotice] = useState<string>("");

  const [tabularFile, setTabularFile] = useState<File | null>(null);
  const [tabularDisplayName, setTabularDisplayName] = useState("");
  const [tabularPreview, setTabularPreview] = useState<TabularPreview | null>(null);
  const [isTabularModalOpen, setIsTabularModalOpen] = useState(false);
  const [csvLat, setCsvLat] = useState("");
  const [csvLon, setCsvLon] = useState("");
  const [deleteConfirmTarget, setDeleteConfirmTarget] = useState<{ id: number; label: string } | null>(null);

  const [errorModal, setErrorModal] = useState<ErrorModalState>({
    open: false,
    title: "",
    message: ""
  });
  const errorModalRef = useRef<HTMLDivElement | null>(null);
  const tabularModalRef = useRef<HTMLDivElement | null>(null);

  const queryClient = useQueryClient();

  const closeErrorModal = () => {
    setErrorModal((prev) => ({ ...prev, open: false }));
  };

  const closeTabularModal = () => {
    setIsTabularModalOpen(false);
  };

  useModalA11y({ open: errorModal.open, onClose: closeErrorModal, modalRef: errorModalRef });
  useModalA11y({ open: isTabularModalOpen, onClose: closeTabularModal, modalRef: tabularModalRef });

  const uploadsQuery = useQuery({
    queryKey: ["uploads", page, sortBy, sortDir],
    queryFn: () => fetchUploads({ page, pageSize: 20, query: "", sortBy, sortDir })
  });

  const openErrorModal = (title: string, message: string, details?: string[]) => {
    setIsTabularModalOpen(false);
    setErrorModal({ open: true, title, message, details });
  };

  const uploadMutation = useMutation({
    mutationFn: createUploads,
    onSuccess: (result) => {
      const successCount = result.success_items.length;
      const failedCount = result.failed_items.length;
      const messageParts = [`업로드/변환 성공 ${successCount}건`];
      if (failedCount > 0) {
        messageParts.push(`실패 ${failedCount}건`);
      }
      setUploadNotice(messageParts.join(" · "));
      queryClient.invalidateQueries({ queryKey: ["uploads"] });
      queryClient.invalidateQueries({ queryKey: ["datasets"] });

      if (failedCount > 0) {
        openErrorModal(
          "업로드 중 일부 항목 실패",
          "일부 파일은 변환에 실패하여 저장되지 않았습니다.",
          result.failed_items.map((item) => `${item.name}: ${item.user_message || item.message || "알 수 없는 오류"}`)
        );
      }
    },
    onError: (error) => {
      const msg = toErrorMessage(error, "업로드 처리 중 오류가 발생했습니다.");
      const lines = msg.split("\n").map((line) => line.trim()).filter(Boolean);
      openErrorModal("업로드 실패", lines[0] || "업로드 처리 중 오류가 발생했습니다.", lines.slice(1));
    }
  });

  const inspectMutation = useMutation({
    mutationFn: inspectTabularUpload,
    onSuccess: (result) => {
      setTabularPreview(result);
      const nextLat = result.suggested_lat ?? result.columns[0] ?? "";
      const nextLon = result.suggested_lon ?? result.columns[Math.min(1, result.columns.length - 1)] ?? "";
      setCsvLat(nextLat);
      setCsvLon(nextLon);
      setIsTabularModalOpen(true);
    },
    onError: (error) => {
      const msg = toErrorMessage(error, "컬럼 정보를 읽지 못했습니다.");
      const lines = msg.split("\n").map((line) => line.trim()).filter(Boolean);
      openErrorModal("CSV/Excel 분석 실패", lines[0] || "컬럼 정보를 읽지 못했습니다.", lines.slice(1));
      setTabularFile(null);
      setTabularPreview(null);
    }
  });

  const submitTabularMutation = useMutation({
    mutationFn: submitTabularUpload,
    onSuccess: () => {
      setUploadNotice("CSV/Excel 업로드 및 변환 완료");
      setIsTabularModalOpen(false);
      setTabularFile(null);
      setTabularPreview(null);
      queryClient.invalidateQueries({ queryKey: ["uploads"] });
      queryClient.invalidateQueries({ queryKey: ["datasets"] });
    },
    onError: (error) => {
      const msg = toErrorMessage(error, "CSV/Excel 변환 중 오류가 발생했습니다.");
      const lines = msg.split("\n").map((line) => line.trim()).filter(Boolean);
      openErrorModal("CSV/Excel 변환 실패", lines[0] || "CSV/Excel 변환 중 오류가 발생했습니다.", lines.slice(1));
    }
  });

  const deleteMutation = useMutation({
    mutationFn: deleteUpload,
    onSuccess: () => {
      setUploadNotice("항목이 삭제되었습니다.");
      queryClient.invalidateQueries({ queryKey: ["uploads"] });
      queryClient.invalidateQueries({ queryKey: ["datasets"] });
    },
    onError: (error) => {
      const msg = toErrorMessage(error, "항목 삭제 중 오류가 발생했습니다.");
      const lines = msg.split("\n").map((line) => line.trim()).filter(Boolean);
      openErrorModal("삭제 실패", lines[0] || "항목 삭제 중 오류가 발생했습니다.", lines.slice(1));
    }
  });

  const rows = useMemo(() => {
    const items = uploadsQuery.data?.items ?? [];
    const statusText = (status?: string) => {
      if (!status) return "완료";
      if (status === "succeeded") return "완료";
      if (status === "failed") return "실패";
      if (status === "running") return "진행중";
      if (status === "queued") return "대기중";
      return status;
    };

    return items.map((item) => ({
      action: (
        <button
          className="icon-btn danger"
          onClick={() => setDeleteConfirmTarget({ id: item.file_id, label: item.name })}
          aria-label="삭제"
          title="삭제"
          disabled={deleteMutation.isPending}
        >
          🗑️
        </button>
      ),
      id: item.id,
      name: <strong>{item.name}</strong>,
      size: formatMb(item.size_bytes),
      status: statusText(item.conversion_status),
      output: item.conversion_output_name ? trimFileNameToSeconds(item.conversion_output_name) : "-",
      rows: item.conversion_output_file_id ? (item.conversion_output_rows ?? 0).toLocaleString() : "-",
      created: item.created_at,
      path: item.path,
      error: item.conversion_error || "-"
    }));
  }, [uploadsQuery.data?.items, deleteMutation.isPending]);

  const onSortChange = (nextSortBy: string) => {
    setPage(1);
    if (sortBy === nextSortBy) {
      setSortDir((prev) => (prev === "asc" ? "desc" : "asc"));
      return;
    }
    setSortBy(nextSortBy);
    setSortDir(nextSortBy === "created_at" ? "desc" : "asc");
  };

  const currentPageSizeMb = useMemo(
    () =>
      (uploadsQuery.data?.items ?? []).reduce((acc, item) => acc + (Number(item.size_bytes) || 0), 0) /
      (1024 * 1024),
    [uploadsQuery.data?.items]
  );
  const currentPageConvertedSizeMb = useMemo(
    () =>
      (uploadsQuery.data?.items ?? []).reduce(
        (acc, item) => acc + (Number(item.conversion_output_size) || 0),
        0
      ) /
      (1024 * 1024),
    [uploadsQuery.data?.items]
  );

  const handleAutoUpload = (files: FileList | null) => {
    if (!files || files.length === 0) {
      return;
    }
    if (uploadMutation.isPending || inspectMutation.isPending || submitTabularMutation.isPending) {
      openErrorModal("작업 진행 중", "현재 업로드/변환 작업이 진행 중입니다. 잠시 후 다시 시도해 주세요.");
      return;
    }

    const pickedFiles = Array.from(files);
    const tabularFiles = pickedFiles.filter((file) => ["csv", "xlsx", "xls"].includes(fileExtension(file.name)));
    const hasFolderSelection = pickedFiles.some((file) => {
      const path = (file as unknown as { webkitRelativePath?: string }).webkitRelativePath;
      return Boolean(path && path.includes("/"));
    });
    if (hasFolderSelection) {
      openErrorModal(
        "폴더 업로드 미지원",
        "폴더 업로드는 지원하지 않습니다.",
        ["Shapefile은 .shp/.dbf/.shx/.prj 구성을 ZIP으로 압축해 업로드해 주세요."]
      );
      return;
    }

    if (tabularFiles.length > 0) {
      if (pickedFiles.length > 1) {
        openErrorModal(
          "CSV/Excel 업로드 방식 안내",
          "CSV/Excel은 한 번에 1개 파일만 업로드할 수 있습니다.",
          ["CSV/Excel 파일을 단독으로 선택하면 컬럼 지정 팝업이 열립니다."]
        );
        return;
      }

      const file = tabularFiles[0];
      setUploadNotice("");
      setTabularFile(file);
      setTabularDisplayName(file.name.replace(/\.[^.]+$/, "").trim());
      inspectMutation.mutate(file);
      return;
    }

    const invalidFiles = pickedFiles.filter((file) => fileExtension(file.name) !== "zip");
    if (invalidFiles.length > 0) {
      openErrorModal(
        "지원하지 않는 파일 형식",
        "ZIP, CSV, XLSX, XLS 파일만 업로드할 수 있습니다.",
        invalidFiles.map((file) => file.name)
      );
      return;
    }

    const displayNames = pickedFiles.map((file) => file.name.replace(/\.[^.]+$/, "").trim());

    setUploadNotice(`선택 ${pickedFiles.length}개 · 업로드 시작`);
    uploadMutation.mutate({ files: pickedFiles, displayNames, outputFormat });
  };

  return (
    <section className="tab-section">
      <LoadingModal
        open={uploadMutation.isPending || inspectMutation.isPending || submitTabularMutation.isPending}
        title={uploadMutation.isPending ? "업로드/변환 중..." : "파일 분석/변환 중..."}
        description="요청을 처리하는 동안 잠시만 기다려 주세요."
      />

      <DeleteConfirmDialog
        open={Boolean(deleteConfirmTarget)}
        dialogId="upload-delete-dialog-title"
        title="업로드 항목 삭제"
        message="삭제하면 즉시 목록에서 제거됩니다. 계속하시겠습니까?"
        targetLabel={deleteConfirmTarget?.label}
        confirmLabel="삭제"
        onCancel={() => setDeleteConfirmTarget(null)}
        onConfirm={() => {
          if (!deleteConfirmTarget) return;
          deleteMutation.mutate(deleteConfirmTarget.id);
          setDeleteConfirmTarget(null);
        }}
      />

      {errorModal.open && (
        <div className="dialog-backdrop" role="presentation">
          <div
            ref={errorModalRef}
            className="dialog-card"
            role="dialog"
            aria-modal="true"
            aria-labelledby="upload-error-dialog-title"
            tabIndex={-1}
          >
            <div className="dialog-head">
              <h4 id="upload-error-dialog-title">{errorModal.title}</h4>
              <button className="icon-btn" onClick={closeErrorModal} aria-label="닫기">
                ✕
              </button>
            </div>
            <p>{errorModal.message}</p>
            {errorModal.details && errorModal.details.length > 0 && (
              <div className="preview-table-wrap" style={{ maxHeight: "240px" }}>
                <table className="preview-table">
                  <tbody>
                    {errorModal.details.map((detail, idx) => (
                      <tr key={`err-${idx}`}>
                        <td>{detail}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <div className="dialog-actions">
              <button className="primary" onClick={closeErrorModal}>
                확인
              </button>
            </div>
          </div>
        </div>
      )}

      {isTabularModalOpen && tabularFile && tabularPreview && (
        <div className="dialog-backdrop" role="presentation">
          <div
            ref={tabularModalRef}
            className="dialog-card tabular-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="upload-tabular-dialog-title"
            tabIndex={-1}
          >
            <div className="dialog-head">
              <h4 id="upload-tabular-dialog-title">위도/경도 컬럼 설정 - {tabularDisplayName}</h4>
              <button className="icon-btn" onClick={closeTabularModal} aria-label="닫기">
                ✕
              </button>
            </div>
            <p className="section-help">CSV/Excel 입력 좌표계는 EPSG:4326(고정)입니다.</p>
            <div className="tabular-guide-card">
              <strong>참고 범위</strong>
              <span>
                위도: {tabularPreview.lat_reference.min} ~ {tabularPreview.lat_reference.max}
              </span>
              <span>
                경도: {tabularPreview.lon_reference.min} ~ {tabularPreview.lon_reference.max}
              </span>
            </div>
            <div className="row">
              <label className="input-group">
                <span>위도 컬럼</span>
                <select value={csvLat} onChange={(e) => setCsvLat(e.target.value)}>
                  {tabularPreview.columns.map((col) => (
                    <option key={`lat-${col}`} value={col}>
                      {col}
                    </option>
                  ))}
                </select>
              </label>
              <label className="input-group">
                <span>경도 컬럼</span>
                <select value={csvLon} onChange={(e) => setCsvLon(e.target.value)}>
                  {tabularPreview.columns.map((col) => (
                    <option key={`lon-${col}`} value={col}>
                      {col}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="preview-table-wrap tabular-preview-wrap">
              <table className="preview-table">
                <thead>
                  <tr>
                    {tabularPreview.columns.map((col) => (
                      <th key={`sample-${col}`}>{col}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {tabularPreview.sample_rows.map((row, idx) => (
                    <tr key={`sample-row-${idx}`}>
                      {tabularPreview.columns.map((col) => (
                        <td key={`sample-${idx}-${col}`}>{String(row[col] ?? "")}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="dialog-actions">
              <button className="ghost" onClick={closeTabularModal}>
                취소
              </button>
              <button
                className="primary"
                disabled={!csvLat || !csvLon || submitTabularMutation.isPending}
                onClick={() => {
                  submitTabularMutation.mutate({
                    file: tabularFile,
                    displayName: tabularDisplayName,
                    output_format: outputFormat,
                    csv_lat_col: csvLat,
                    csv_lon_col: csvLon,
                    csv_input_crs: "EPSG:4326"
                  });
                }}
              >
                업로드 + 변환 실행
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="panel upload-studio-panel">
        <div className="upload-studio-head">
          <div className="upload-studio-copy">
            <span className="upload-kicker">UPLOAD COMMAND CENTER</span>
            <h3>원본 업로드 & 즉시 변환</h3>
            <p className="section-help upload-section-help">
              ZIP은 즉시 파이프라인으로 전달되고, CSV/Excel은 컬럼 분석 후 정확히 변환됩니다.
            </p>
          </div>
          <div className="upload-format-shell">
            <div className="input-group">
              <span>업로드 결과 출력 형식</span>
              <div className="format-toggle">
                <button
                  type="button"
                  className={outputFormat === "geoparquet" ? "format-btn active" : "format-btn"}
                  onClick={() => setOutputFormat("geoparquet")}
                  disabled={uploadMutation.isPending || inspectMutation.isPending || submitTabularMutation.isPending}
                >
                  <span className="format-btn-title">GeoParquet</span>
                  <span className="format-btn-sub">분석 최적</span>
                </button>
                <button
                  type="button"
                  className={outputFormat === "gpkg" ? "format-btn active" : "format-btn"}
                  onClick={() => setOutputFormat("gpkg")}
                  disabled={uploadMutation.isPending || inspectMutation.isPending || submitTabularMutation.isPending}
                >
                  <span className="format-btn-title">GPKG</span>
                  <span className="format-btn-sub">호환 중점</span>
                </button>
              </div>
            </div>
          </div>
        </div>

        <div className="upload-workflow" aria-hidden="true">
          <div className="upload-workflow-step">
            <span>01</span>
            <strong>원본 선택</strong>
            <p>ZIP 또는 CSV/Excel 파일을 선택하고 형식을 확인합니다.</p>
          </div>
          <div className="upload-workflow-step">
            <span>02</span>
            <strong>검증 & 분석</strong>
            <p>Shapefile bundle·위경도 컬럼 유효성을 자동으로 확인합니다.</p>
          </div>
          <div className="upload-workflow-step">
            <span>03</span>
            <strong>즉시 변환</strong>
            <p>성공 시 raw/data를 동기화 저장하고 결과를 즉시 갱신합니다.</p>
          </div>
        </div>

        <div className="upload-picker-grid">
          <label className="upload-tile upload-tile-file">
            <input
              className="file-hidden"
              type="file"
              multiple
              accept=".zip,.csv,.xlsx,.xls"
              disabled={uploadMutation.isPending || inspectMutation.isPending || submitTabularMutation.isPending}
              onChange={(e) => {
                handleAutoUpload(e.target.files);
                e.currentTarget.value = "";
              }}
            />
            <div className="upload-tile-head">
              <span className="upload-tile-icon" aria-hidden="true">
                ⬢
              </span>
              <div>
                <div className="upload-tile-title">파일 업로드</div>
                <p>Shapefile ZIP은 즉시 변환되고 CSV/Excel은 컬럼 지정 모달로 이어집니다.</p>
              </div>
            </div>
            <div className="upload-tile-foot">
              <span className="upload-tile-cta">파일 선택</span>
              <span className="upload-tile-meta">ZIP · CSV · XLSX · XLS</span>
            </div>
          </label>
        </div>

        {uploadNotice && (
          <p className="upload-notice" aria-live="polite">
            {uploadNotice}
          </p>
        )}
      </div>

      <div className="panel upload-results-panel">
        <div className="metric-strip upload-metric-strip">
          <div className="metric-card upload-stat-card">
            <span className="metric-label">총 업로드</span>
            <strong className="metric-value">{uploadsQuery.data?.total_items ?? 0}건</strong>
          </div>
          <div className="metric-card upload-stat-card dual-size-card">
            <span className="metric-label">현재 페이지 용량</span>
            <div className="size-grid">
              <div className="size-chip">
                <span className="size-chip-label">rawdata</span>
                <strong className="size-chip-value">{currentPageSizeMb.toFixed(2)} MB</strong>
              </div>
              <div className="size-chip">
                <span className="size-chip-label">data</span>
                <strong className="size-chip-value">{currentPageConvertedSizeMb.toFixed(2)} MB</strong>
              </div>
            </div>
          </div>
        </div>

        <div className="upload-results-head">
          <h3>업로드 목록 (원본 + 자동 변환 상태)</h3>
          <span className="scroll-hint-badge table-scroll-hint">↔ 좌우 스크롤</span>
          <p className="section-help">업로드와 변환은 원자적으로 처리됩니다. 실패 시 저장되지 않습니다.</p>
        </div>

        <DataTable
          columns={[
            { key: "action", title: "관리", width: "84px", align: "center" },
            { key: "id", title: "번호", width: "76px", sortable: true, sortKey: "id" },
            { key: "name", title: "이름", width: "180px", sortable: true, sortKey: "name" },
            { key: "size", title: "용량", width: "140px", sortable: true, sortKey: "size_bytes" },
            { key: "status", title: "변환상태", width: "130px", sortable: true, sortKey: "conversion_status" },
            { key: "output", title: "결과파일", width: "220px", sortable: true, sortKey: "conversion_output_name" },
            { key: "rows", title: "변환 행수", width: "120px", sortable: true, sortKey: "conversion_output_rows", align: "right" },
            { key: "created", title: "생성 시각", width: "196px", sortable: true, sortKey: "created_at" },
            { key: "path", title: "원본 경로", width: "260px", sortable: true, sortKey: "path" },
            { key: "error", title: "오류", width: "220px", sortable: true, sortKey: "conversion_error" }
          ]}
          rows={rows}
          emptyText="업로드된 항목이 없습니다."
          sortBy={sortBy}
          sortDir={sortDir}
          onSortChange={onSortChange}
        />

        <PaginationRow
          page={page}
          totalPages={uploadsQuery.data?.total_pages ?? 1}
          totalItems={uploadsQuery.data?.total_items ?? 0}
          onPrev={() => setPage((p) => Math.max(1, p - 1))}
          onNext={() => setPage((p) => Math.min(uploadsQuery.data?.total_pages ?? 1, p + 1))}
        />
      </div>
    </section>
  );
}
