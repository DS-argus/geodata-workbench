import { useMemo, useState } from "react";
import type { PathOptions } from "leaflet";
import L from "leaflet";
import { useQuery } from "@tanstack/react-query";
import MarkerClusterGroup from "react-leaflet-markercluster";
import { GeoJSON, MapContainer, Marker, TileLayer, Tooltip } from "react-leaflet";
import { fetchDatasetGeojson, fetchDatasetPreview, fetchDatasets } from "../api";

const PREVIEW_LIMIT = 50;
type AnyFeature = GeoJSON.Feature<GeoJSON.Geometry, Record<string, unknown>>;
type AnyFeatureCollection = GeoJSON.FeatureCollection<GeoJSON.Geometry, Record<string, unknown>>;

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function tooltipHtml(props: Record<string, unknown> | undefined): string {
  if (!props) {
    return "";
  }
  return Object.entries(props)
    .map(([k, v]) => {
      const key = escapeHtml(k);
      const value = escapeHtml(v === null ? "" : String(v));
      return `<div><strong>${key}</strong>: ${value}</div>`;
    })
    .join("");
}

function splitGeoFeatures(collection: AnyFeatureCollection | null): {
  pointFeatures: AnyFeature[];
  vectorFeatures: AnyFeature[];
} {
  if (!collection?.features?.length) {
    return { pointFeatures: [], vectorFeatures: [] };
  }

  const pointFeatures: AnyFeature[] = [];
  const vectorFeatures: AnyFeature[] = [];

  collection.features.forEach((feature) => {
    if (!feature.geometry) {
      return;
    }
    const geometryType = feature.geometry.type;
    if (geometryType === "Point") {
      pointFeatures.push(feature);
      return;
    }
    if (geometryType === "MultiPoint") {
      const coords = (feature.geometry as GeoJSON.MultiPoint).coordinates ?? [];
      coords.forEach((coordinate) => {
        pointFeatures.push({
          ...feature,
          geometry: { type: "Point", coordinates: coordinate }
        });
      });
      return;
    }
    vectorFeatures.push(feature);
  });

  return { pointFeatures, vectorFeatures };
}

function vectorStyle(feature?: AnyFeature): PathOptions {
  const geometryType = feature?.geometry?.type;
  if (geometryType === "Polygon" || geometryType === "MultiPolygon") {
    return {
      color: "#0f4bcc",
      weight: 1.4,
      fillColor: "#1f6feb",
      fillOpacity: 0.68
    };
  }
  if (geometryType === "LineString" || geometryType === "MultiLineString") {
    return {
      color: "#0f4bcc",
      weight: 2.6,
      opacity: 0.96
    };
  }
  return {
    color: "#0f4bcc",
    weight: 1.4,
    fillColor: "#1f6feb",
    fillOpacity: 0.55
  };
}

export function BrowseTab() {
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [displayRows, setDisplayRows] = useState(1000);

  const datasetsQuery = useQuery({ queryKey: ["datasets"], queryFn: fetchDatasets });
  const datasets = datasetsQuery.data ?? [];
  const effectiveId = selectedId;

  const previewQuery = useQuery({
    queryKey: ["dataset-preview", effectiveId],
    queryFn: () => fetchDatasetPreview(effectiveId as number, PREVIEW_LIMIT),
    enabled: effectiveId !== null
  });

  const geoQuery = useQuery({
    queryKey: ["dataset-geojson", effectiveId, displayRows],
    queryFn: () => fetchDatasetGeojson(effectiveId as number, displayRows),
    enabled: effectiveId !== null
  });

  const selectedDataset = useMemo(
    () => datasets.find((item) => item.file_id === effectiveId),
    [datasets, effectiveId]
  );
  const geojsonData = (geoQuery.data as AnyFeatureCollection | undefined) ?? null;
  const { pointFeatures, vectorFeatures } = useMemo(() => splitGeoFeatures(geojsonData), [geojsonData]);
  const pointIcon = useMemo(
    () =>
      L.divIcon({
        className: "point-dot-icon",
        html: "<span></span>",
        iconSize: [12, 12],
        iconAnchor: [6, 6]
      }),
    []
  );
  const mapLoading = geoQuery.isLoading || geoQuery.isFetching;

  return (
    <section className="tab-section">
      <div className="panel">
        <div className="row">
          <label className="input-group">
            <span>파일 선택</span>
            <select
              value={effectiveId ?? ""}
              onChange={(e) => setSelectedId(e.target.value ? Number(e.target.value) : null)}
            >
              <option value="">없음</option>
              {datasets.map((item) => (
                <option key={item.file_id} value={item.file_id}>
                  {item.display_name} ({item.total_rows.toLocaleString()} rows)
                </option>
              ))}
            </select>
          </label>
        </div>
        <p className="section-help">파일을 선택하면 속성 미리보기와 지도가 함께 표시됩니다.</p>
      </div>

      <div className="browse-grid">
        <div className="panel preview-panel">
          <div className="preview-head">
            <h3>Preview</h3>
            <span className="scroll-hint-badge">↔ 좌우 스크롤</span>
          </div>
          <div className="preview-meta">{selectedDataset?.name ?? ""}</div>
          {!effectiveId ? (
            <div className="preview-empty">파일을 선택하면 상위 50개 행을 미리 볼 수 있습니다.</div>
          ) : (
            <div className="preview-table-wrap">
              <table className="preview-table">
                <thead>
                  <tr>
                    {(previewQuery.data?.columns ?? []).map((col) => (
                      <th key={col}>{col}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(previewQuery.data?.rows ?? []).map((row, idx) => (
                    <tr key={idx}>
                      {(previewQuery.data?.columns ?? []).map((col) => (
                        <td key={`${idx}-${col}`}>{String(row[col] ?? "")}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="panel map-panel">
          <div className="row between map-head">
            <h3>Map</h3>
            <label className="map-rows-control">
              <span>지도 표시 행 수</span>
              <input
                type="number"
                min={1}
                step={100}
                value={displayRows}
                onChange={(e) => setDisplayRows(Number(e.target.value) || 1)}
              />
            </label>
          </div>
          <div className="map-box">
            {mapLoading && (
              <div className="map-loading-overlay">
                <div className="loading-spinner map-inline-spinner" />
                <span>지도 데이터를 불러오는 중</span>
              </div>
            )}
            <div className="map-legend">
              <span>● Point: Cluster</span>
              <span>■ Polygon: 채움 표시</span>
            </div>
            <MapContainer center={[37.5665, 126.978]} zoom={7} style={{ width: "100%", height: "100%" }}>
              <TileLayer
                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              />
              {pointFeatures.length > 0 && (
                <MarkerClusterGroup chunkedLoading>
                  {pointFeatures.map((feature, index) => {
                    const coordinates = (feature.geometry as GeoJSON.Point).coordinates;
                    if (!Array.isArray(coordinates) || coordinates.length < 2) {
                      return null;
                    }
                    const lng = Number(coordinates[0]);
                    const lat = Number(coordinates[1]);
                    if (!Number.isFinite(lng) || !Number.isFinite(lat)) {
                      return null;
                    }
                    const text = tooltipHtml(feature.properties as Record<string, unknown> | undefined);
                    return (
                      <Marker key={`pt-${index}-${lat}-${lng}`} position={[lat, lng]} icon={pointIcon}>
                        {text.length > 0 ? (
                          <Tooltip sticky className="feature-tooltip">
                            <div dangerouslySetInnerHTML={{ __html: text }} />
                          </Tooltip>
                        ) : null}
                      </Marker>
                    );
                  })}
                </MarkerClusterGroup>
              )}
              {vectorFeatures.length > 0 && (
                <GeoJSON
                  data={{ type: "FeatureCollection", features: vectorFeatures } as AnyFeatureCollection}
                  style={vectorStyle}
                  onEachFeature={(feature, layer) => {
                    const text = tooltipHtml(feature.properties as Record<string, unknown> | undefined);
                    if (text.length > 0) {
                      layer.bindTooltip(text, { sticky: true, className: "feature-tooltip" });
                    }
                  }}
                />
              )}
            </MapContainer>
          </div>
        </div>
      </div>
    </section>
  );
}
