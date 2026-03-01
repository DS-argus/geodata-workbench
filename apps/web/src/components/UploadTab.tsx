import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createUploads, deleteUpload, fetchUploads } from "../api";
import { toErrorMessage } from "../error";
import { LoadingModal } from "./LoadingModal";
import { DataTable, formatMb, PaginationRow } from "./TableShell";

export function UploadTab() {
  const [page, setPage] = useState(1);
  const [uploadNotice, setUploadNotice] = useState<string>("");
  const [uploadError, setUploadError] = useState<string>("");
  const queryClient = useQueryClient();

  const uploadsQuery = useQuery({
    queryKey: ["uploads", page],
    queryFn: () => fetchUploads({ page, pageSize: 20, query: "" })
  });

  const uploadMutation = useMutation({
    mutationFn: createUploads,
    onSuccess: (result) => {
      setUploadError("");
      setUploadNotice(`업로드 완료 (${result.saved_count}건)`);
      queryClient.invalidateQueries({ queryKey: ["uploads"] });
      queryClient.invalidateQueries({ queryKey: ["convert-options"] });
    },
    onError: (error) => {
      setUploadNotice("");
      setUploadError(toErrorMessage(error, "업로드 실패"));
    }
  });

  const deleteMutation = useMutation({
    mutationFn: deleteUpload,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["uploads"] });
      queryClient.invalidateQueries({ queryKey: ["convert-options"] });
    }
  });

  const rows = useMemo(() => {
    const items = uploadsQuery.data?.items ?? [];
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
      created: item.created_at,
      path: item.path
    }));
  }, [uploadsQuery.data?.items, deleteMutation]);
  const currentPageSizeMb = useMemo(
    () =>
      (uploadsQuery.data?.items ?? []).reduce((acc, item) => acc + (Number(item.size_bytes) || 0), 0) /
      (1024 * 1024),
    [uploadsQuery.data?.items]
  );

  const handleAutoUpload = (files: FileList | null) => {
    if (!files || files.length === 0) {
      return;
    }
    if (uploadMutation.isPending) {
      setUploadError("업로드 진행 중입니다. 잠시 후 다시 시도하세요.");
      return;
    }

    const pickedFiles = Array.from(files);
    const relativePaths = pickedFiles.map((file) => {
      const path = (file as unknown as { webkitRelativePath?: string }).webkitRelativePath;
      return path && path.length > 0 ? path : file.name;
    });
    const displayNames = pickedFiles.map((file, index) => {
      const relativePath = relativePaths[index];
      if (relativePath.includes("/")) {
        return "";
      }
      return file.name.replace(/\.[^.]+$/, "").trim();
    });

    setUploadError("");
    setUploadNotice(`선택 ${pickedFiles.length}개 · 업로드 시작`);
    uploadMutation.mutate({ files: pickedFiles, relativePaths, displayNames });
  };

  return (
    <section className="tab-section">
      <LoadingModal
        open={uploadMutation.isPending}
        title="업로드 중..."
        description="파일을 저장하고 메타데이터를 생성하고 있습니다."
      />

      <div className="panel">
        <div className="upload-picker-grid">
          <label className="upload-tile">
            <input
              className="file-hidden"
              type="file"
              multiple
              accept=".zip,.csv,.xlsx,.xls"
              disabled={uploadMutation.isPending}
              onChange={(e) => {
                handleAutoUpload(e.target.files);
                e.currentTarget.value = "";
              }}
            />
            <div className="upload-tile-title">파일 업로드</div>
            <p>CSV / Excel / ZIP 파일을 선택하면 즉시 저장됩니다.</p>
            <span className="upload-tile-cta">파일 선택</span>
          </label>

          <label className="upload-tile">
            <input
              className="file-hidden"
              type="file"
              multiple
              disabled={uploadMutation.isPending}
              onChange={(e) => {
                handleAutoUpload(e.target.files);
                e.currentTarget.value = "";
              }}
              {...({ webkitdirectory: "", directory: "" } as any)}
            />
            <div className="upload-tile-title">폴더 업로드</div>
            <p>Shapefile 구성 파일이 포함된 폴더를 선택하면 즉시 저장됩니다.</p>
            <span className="upload-tile-cta">폴더 선택</span>
          </label>
        </div>

        {uploadNotice && <p className="info">{uploadNotice}</p>}
        {uploadError && <p className="error">{uploadError}</p>}
      </div>

      <div className="panel">
        <div className="metric-strip">
          <div className="metric-card">
            <span className="metric-label">총 업로드</span>
            <strong className="metric-value">{uploadsQuery.data?.total_items ?? 0}건</strong>
          </div>
          <div className="metric-card">
            <span className="metric-label">현재 페이지 용량</span>
            <strong className="metric-value">{currentPageSizeMb.toFixed(2)} MB</strong>
          </div>
        </div>

        <h3>업로드 목록</h3>
        <p className="section-help">원본 파일을 확인하고 필요 시 행 단위로 삭제할 수 있습니다.</p>

        <DataTable
          columns={[
            { key: "action", title: "관리", width: "84px", align: "center" },
            { key: "id", title: "번호", width: "76px" },
            { key: "name", title: "이름", width: "240px" },
            { key: "size", title: "용량", width: "140px" },
            { key: "created", title: "생성 시각", width: "196px" },
            { key: "path", title: "경로" }
          ]}
          rows={rows}
          emptyText="업로드된 항목이 없습니다."
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
