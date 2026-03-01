import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  cancelConversionJob,
  deleteConversion,
  fetchConversionJob,
  fetchConvertInputColumns,
  fetchConversions,
  fetchConvertOptions,
  startConversion
} from "../api";
import { toErrorMessage } from "../error";
import { DataTable, formatMb, PaginationRow } from "./TableShell";
import { LoadingModal } from "./LoadingModal";

const CRS_PRESETS = [
  { code: "EPSG:4326", title: "WGS 84", description: "GPS와 웹 API에서 가장 보편적으로 사용하는 경위도 좌표계" },
  { code: "EPSG:3857", title: "Web Mercator", description: "OSM/대부분의 웹지도 타일에서 사용되는 좌표계" },
  { code: "EPSG:5179", title: "Korea 2000 / Unified CS", description: "국내 분석에서 자주 쓰는 미터 단위 좌표계" },
  { code: "EPSG:5186", title: "Korea 2000 / Central Belt", description: "국토정보 데이터에서 자주 보이는 중부원점 계열" },
  { code: "EPSG:32652", title: "UTM Zone 52N", description: "동아시아 북반구 UTM 기반 분석 좌표계" }
];

export function ConvertTab() {
  const [page, setPage] = useState(1);
  const [selectedInput, setSelectedInput] = useState<number | null>(null);
  const [outputFormat, setOutputFormat] = useState("geoparquet");
  const [crsHandling, setCrsHandling] = useState<"keep" | "transform">("keep");
  const [targetCrs, setTargetCrs] = useState("EPSG:4326");
  const [csvLat, setCsvLat] = useState("lat");
  const [csvLon, setCsvLon] = useState("lon");
  const [csvInputCrs, setCsvInputCrs] = useState("EPSG:4326");
  const [convertNotice, setConvertNotice] = useState("");
  const [convertError, setConvertError] = useState("");
  const [isCrsModalOpen, setIsCrsModalOpen] = useState(false);
  const [isTabularModalOpen, setIsTabularModalOpen] = useState(false);
  const [runningJobId, setRunningJobId] = useState<number | null>(null);
  const [isCancelling, setIsCancelling] = useState(false);
  const [tabularConfiguredFileId, setTabularConfiguredFileId] = useState<number | null>(null);
  const previousCrsHandling = useRef(crsHandling);

  const queryClient = useQueryClient();
  const optionsQuery = useQuery({
    queryKey: ["convert-options"],
    queryFn: fetchConvertOptions
  });
  const conversionsQuery = useQuery({
    queryKey: ["conversions", page],
    queryFn: () => fetchConversions({ page, pageSize: 20, query: "" })
  });

  const startMutation = useMutation({
    mutationFn: startConversion,
    onSuccess: (result) => {
      setRunningJobId(result.job_id);
    },
    onError: (error) => {
      setConvertNotice("");
      setConvertError(toErrorMessage(error, "변환 실패"));
    }
  });

  const deleteMutation = useMutation({
    mutationFn: deleteConversion,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["conversions"] });
      queryClient.invalidateQueries({ queryKey: ["datasets"] });
    }
  });

  const cancelMutation = useMutation({
    mutationFn: cancelConversionJob,
    onSuccess: () => {
      setIsCancelling(true);
      setConvertError("");
      setConvertNotice("중단 요청을 전송했습니다. 현재 단계를 마친 후 작업이 중단됩니다.");
    },
    onError: (error) => {
      setConvertError(toErrorMessage(error, "중단 요청 실패"));
    }
  });

  const runningJobQuery = useQuery({
    queryKey: ["conversion-job", runningJobId],
    queryFn: () => fetchConversionJob(runningJobId as number),
    enabled: runningJobId !== null,
    refetchInterval: runningJobId !== null ? 1000 : false
  });

  const options = optionsQuery.data ?? [];

  useEffect(() => {
    if (!options.length) {
      setSelectedInput(null);
      return;
    }
    if (selectedInput === null || !options.some((opt) => opt.file_id === selectedInput)) {
      setSelectedInput(options[0].file_id);
    }
  }, [options, selectedInput]);

  useEffect(() => {
    if (previousCrsHandling.current !== crsHandling && crsHandling === "transform") {
      setIsCrsModalOpen(true);
    }
    previousCrsHandling.current = crsHandling;
  }, [crsHandling]);

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
      setConvertError("");
      setConvertNotice("변환이 완료되었습니다.");
      queryClient.invalidateQueries({ queryKey: ["conversions"] });
      queryClient.invalidateQueries({ queryKey: ["datasets"] });
      return;
    }
    if (status === "cancelled") {
      setConvertError("");
      setConvertNotice("변환이 중단되었습니다.");
      return;
    }

    setConvertNotice("");
    setConvertError(runningJobQuery.data.error_message?.trim() || "변환 실패");
  }, [runningJobId, runningJobQuery.data, queryClient]);

  const currentInput = useMemo(
    () => options.find((opt) => opt.file_id === (selectedInput ?? options[0]?.file_id)),
    [options, selectedInput]
  );
  const isTabular = ["csv", "xlsx", "xls"].includes(currentInput?.format ?? "");

  const tabularColumnsQuery = useQuery({
    queryKey: ["convert-tabular-columns", currentInput?.file_id],
    queryFn: () => fetchConvertInputColumns(currentInput?.file_id as number),
    enabled: isTabular && !!currentInput && isTabularModalOpen
  });

  useEffect(() => {
    if (!isTabular || !currentInput || !tabularColumnsQuery.data) {
      return;
    }
    const columns = tabularColumnsQuery.data.columns;
    if (!columns.length) {
      return;
    }
    if (tabularConfiguredFileId === currentInput.file_id) {
      return;
    }

    const nextLat = tabularColumnsQuery.data.suggested_lat ?? columns[0];
    const nextLon = tabularColumnsQuery.data.suggested_lon ?? columns[Math.min(1, columns.length - 1)] ?? columns[0];
    setCsvLat(nextLat);
    setCsvLon(nextLon);
    setTabularConfiguredFileId(currentInput.file_id);
  }, [isTabular, currentInput, tabularColumnsQuery.data, tabularConfiguredFileId]);

  const rows = useMemo(() => {
    const items = conversionsQuery.data?.items ?? [];
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
      path: item.path,
      crs: item.crs || "-"
    }));
  }, [conversionsQuery.data?.items, deleteMutation]);

  const currentPageSizeMb = useMemo(
    () =>
      (conversionsQuery.data?.items ?? []).reduce(
        (acc, item) => acc + (Number(item.size_bytes) || 0),
        0
      ) / (1024 * 1024),
    [conversionsQuery.data?.items]
  );

  const submitConversion = () => {
    if (!currentInput) {
      return;
    }
    setConvertError("");
    setConvertNotice("변환 요청을 전송했습니다.");
    startMutation.mutate({
      input_file_id: currentInput.file_id,
      output_format: outputFormat,
      crs_handling: crsHandling,
      target_crs: targetCrs,
      csv_lat_col: isTabular ? csvLat : undefined,
      csv_lon_col: isTabular ? csvLon : undefined,
      csv_input_crs: isTabular ? csvInputCrs : undefined
    });
  };

  const latStats = csvLat ? tabularColumnsQuery.data?.numeric_ranges?.[csvLat] : undefined;
  const lonStats = csvLon ? tabularColumnsQuery.data?.numeric_ranges?.[csvLon] : undefined;

  return (
    <section className="tab-section">
      <LoadingModal
        open={startMutation.isPending || runningJobId !== null}
        title="변환 중..."
        description={
          isCancelling
            ? "중단 요청을 처리하고 있습니다. 현재 단계 완료 후 중단됩니다."
            : "입력 데이터를 읽고 출력 파일을 생성하고 있습니다."
        }
        cancelLabel={isCancelling ? "중단 요청 중..." : "중단"}
        cancelDisabled={isCancelling || cancelMutation.isPending}
        onCancel={
          runningJobId !== null
            ? () => {
                if (isCancelling || cancelMutation.isPending) {
                  return;
                }
                cancelMutation.mutate(runningJobId);
              }
            : undefined
        }
      />
      {isCrsModalOpen && (
        <div className="dialog-backdrop" onClick={() => setIsCrsModalOpen(false)}>
          <div className="dialog-card" onClick={(e) => e.stopPropagation()}>
            <div className="dialog-head">
              <h4>목표 CRS 선택</h4>
              <button className="icon-btn" onClick={() => setIsCrsModalOpen(false)} aria-label="닫기">
                ✕
              </button>
            </div>
            <div className="crs-list">
              {CRS_PRESETS.map((preset) => (
                <div key={preset.code} className="crs-item">
                  <div>
                    <strong>{preset.code}</strong>
                    <div className="crs-title">{preset.title}</div>
                    <p>{preset.description}</p>
                  </div>
                  <button
                    className={targetCrs === preset.code ? "primary compact active" : "ghost compact"}
                    onClick={() => {
                      setTargetCrs(preset.code);
                      setIsCrsModalOpen(false);
                    }}
                  >
                    선택
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
      {isTabularModalOpen && isTabular && (
        <div className="dialog-backdrop" onClick={() => setIsTabularModalOpen(false)}>
          <div className="dialog-card tabular-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="dialog-head">
              <h4>위도/경도 컬럼 설정</h4>
              <button className="icon-btn" onClick={() => setIsTabularModalOpen(false)} aria-label="닫기">
                ✕
              </button>
            </div>

            {tabularColumnsQuery.isLoading && <p className="info">컬럼 정보를 불러오는 중입니다...</p>}
            {tabularColumnsQuery.isError && (
              <p className="error">{toErrorMessage(tabularColumnsQuery.error, "컬럼 정보를 불러오지 못했습니다.")}</p>
            )}

            {tabularColumnsQuery.data && (
              <div className="tabular-config-wrap">
                <div className="tabular-guide-card">
                  <strong>참고 범위</strong>
                  <span>
                    위도: {tabularColumnsQuery.data.lat_reference.min} ~ {tabularColumnsQuery.data.lat_reference.max}
                  </span>
                  <span>
                    경도: {tabularColumnsQuery.data.lon_reference.min} ~ {tabularColumnsQuery.data.lon_reference.max}
                  </span>
                </div>

                <div className="row grid-3">
                  <label className="input-group">
                    <span>위도 컬럼</span>
                    <select value={csvLat} onChange={(e) => setCsvLat(e.target.value)}>
                      {tabularColumnsQuery.data.columns.map((col) => (
                        <option key={`lat-${col}`} value={col}>
                          {col}
                        </option>
                      ))}
                    </select>
                    <small className="hint-text">
                      {latStats
                        ? `데이터 범위: ${latStats.min.toFixed(6)} ~ ${latStats.max.toFixed(6)}`
                        : "숫자 범위를 계산할 수 없는 컬럼입니다."}
                    </small>
                  </label>
                  <label className="input-group">
                    <span>경도 컬럼</span>
                    <select value={csvLon} onChange={(e) => setCsvLon(e.target.value)}>
                      {tabularColumnsQuery.data.columns.map((col) => (
                        <option key={`lon-${col}`} value={col}>
                          {col}
                        </option>
                      ))}
                    </select>
                    <small className="hint-text">
                      {lonStats
                        ? `데이터 범위: ${lonStats.min.toFixed(6)} ~ ${lonStats.max.toFixed(6)}`
                        : "숫자 범위를 계산할 수 없는 컬럼입니다."}
                    </small>
                  </label>
                  <label className="input-group">
                    <span>입력 CRS</span>
                    <input value={csvInputCrs} onChange={(e) => setCsvInputCrs(e.target.value)} />
                    <small className="hint-text">예: EPSG:4326, EPSG:5179</small>
                  </label>
                </div>

                <div className="tabular-columns-shell">
                  <h5>컬럼 목록</h5>
                  <div className="tabular-columns-grid">
                    {tabularColumnsQuery.data.columns.map((col) => {
                      const stats = tabularColumnsQuery.data.numeric_ranges[col];
                      return (
                        <div key={col} className="tabular-column-item">
                          <strong>{col}</strong>
                          <span>
                            {stats
                              ? `${stats.min.toFixed(4)} ~ ${stats.max.toFixed(4)}`
                              : "숫자 범위 없음"}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>

                <div className="preview-table-wrap tabular-preview-wrap">
                  <table className="preview-table">
                    <thead>
                      <tr>
                        {tabularColumnsQuery.data.columns.map((col) => (
                          <th key={`sample-${col}`}>{col}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {tabularColumnsQuery.data.sample_rows.map((row, idx) => (
                        <tr key={`sample-row-${idx}`}>
                          {tabularColumnsQuery.data.columns.map((col) => (
                            <td key={`sample-${idx}-${col}`}>{String(row[col] ?? "")}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <div className="dialog-actions">
                  <button className="ghost" onClick={() => setIsTabularModalOpen(false)}>
                    취소
                  </button>
                  <button
                    className="primary"
                    disabled={!csvLat || !csvLon || startMutation.isPending || runningJobId !== null}
                    onClick={() => {
                      setIsTabularModalOpen(false);
                      submitConversion();
                    }}
                  >
                    저장 후 변환 실행
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      <div className="panel">
        <h3>변환 실행</h3>
        <p className="section-help">입력 파일과 CRS 정책을 선택한 뒤 변환을 실행하세요.</p>

        {!options.length && (
          <p className="warn">변환 가능한 입력 파일이 없습니다. Upload 탭에서 먼저 업로드해 주세요.</p>
        )}

        <div className="row grid-5">
          <label className="input-group">
            <span>입력 파일</span>
            <select
              disabled={!options.length}
              value={selectedInput ?? options[0]?.file_id ?? ""}
              onChange={(e) => setSelectedInput(Number(e.target.value))}
            >
              {options.map((opt) => (
                <option key={opt.file_id} value={opt.file_id}>
                  {opt.label}
                </option>
              ))}
            </select>
          </label>

          <label className="input-group">
            <span>출력 형식</span>
            <select value={outputFormat} onChange={(e) => setOutputFormat(e.target.value)}>
              <option value="geoparquet">geoparquet</option>
              <option value="gpkg">gpkg</option>
            </select>
          </label>

          <label className="input-group">
            <span>CRS 처리</span>
            <select value={crsHandling} onChange={(e) => setCrsHandling(e.target.value as "keep" | "transform")}>
              <option value="keep">입력 CRS 유지</option>
              <option value="transform">목표 CRS로 변환</option>
            </select>
          </label>

          {crsHandling === "transform" && (
            <label className="input-group">
              <span>목표 CRS</span>
              <div className="target-crs-box">
                <input value={targetCrs} onChange={(e) => setTargetCrs(e.target.value)} />
                <button className="ghost compact" onClick={() => setIsCrsModalOpen(true)}>
                  CRS 목록
                </button>
              </div>
              <small className="hint-text">예: EPSG:4326 (WGS84), EPSG:5186 (중부원점)</small>
            </label>
          )}

          <button
            className="primary"
            disabled={startMutation.isPending || runningJobId !== null || !currentInput}
            onClick={() => {
              if (!currentInput) {
                return;
              }
              if (isTabular) {
                setIsTabularModalOpen(true);
                return;
              }
              submitConversion();
            }}
          >
            변환 실행
          </button>
        </div>

        {isTabular && (
          <div className="tabular-inline-config">
            <span>
              위도: <strong>{csvLat || "-"}</strong> · 경도: <strong>{csvLon || "-"}</strong> · 입력 CRS:{" "}
              <strong>{csvInputCrs || "-"}</strong>
            </span>
            <button className="ghost compact" onClick={() => setIsTabularModalOpen(true)}>
              위경도 컬럼 설정
            </button>
          </div>
        )}

        {convertNotice && <p className="info">{convertNotice}</p>}
        {convertError && <p className="error">{convertError}</p>}
      </div>

      <div className="panel">
        <div className="metric-strip">
          <div className="metric-card">
            <span className="metric-label">총 변환 데이터</span>
            <strong className="metric-value">{conversionsQuery.data?.total_items ?? 0}건</strong>
          </div>
          <div className="metric-card">
            <span className="metric-label">현재 페이지 용량</span>
            <strong className="metric-value">{currentPageSizeMb.toFixed(2)} MB</strong>
          </div>
          <div className="metric-card">
            <span className="metric-label">입력 가능 파일</span>
            <strong className="metric-value">{options.length}건</strong>
          </div>
        </div>

        <h3>변환 데이터 목록</h3>
        <p className="section-help">생성된 결과 파일을 확인하고 불필요한 항목을 정리할 수 있습니다.</p>

        <DataTable
          columns={[
            { key: "action", title: "관리", width: "84px", align: "center" },
            { key: "id", title: "번호", width: "76px" },
            { key: "name", title: "이름", width: "220px" },
            { key: "size", title: "용량", width: "140px" },
            { key: "created", title: "생성 시각", width: "196px" },
            { key: "path", title: "경로" },
            { key: "crs", title: "좌표계", width: "130px" }
          ]}
          rows={rows}
          emptyText="변환된 데이터가 없습니다."
        />

        <PaginationRow
          page={page}
          totalPages={conversionsQuery.data?.total_pages ?? 1}
          totalItems={conversionsQuery.data?.total_items ?? 0}
          onPrev={() => setPage((p) => Math.max(1, p - 1))}
          onNext={() => setPage((p) => Math.min(conversionsQuery.data?.total_pages ?? 1, p + 1))}
        />
      </div>
    </section>
  );
}
