import { useEffect, useMemo, useState } from "react";
import type { LatLngBoundsExpression, LatLngTuple } from "leaflet";
import { MapContainer, Rectangle, TileLayer, useMap, useMapEvents } from "react-leaflet";

export type BboxTuple = [number, number, number, number]; // [minLon, minLat, maxLon, maxLat]

type WfsBboxPickerProps = {
  value: BboxTuple | null;
  onChange: (bbox: BboxTuple) => void;
};

function bboxToBounds(bbox: BboxTuple): LatLngBoundsExpression {
  const [minLon, minLat, maxLon, maxLat] = bbox;
  return [
    [minLat, minLon],
    [maxLat, maxLon]
  ];
}

function pointsToBbox(start: LatLngTuple, end: LatLngTuple): BboxTuple {
  const minLat = Math.min(start[0], end[0]);
  const maxLat = Math.max(start[0], end[0]);
  const minLon = Math.min(start[1], end[1]);
  const maxLon = Math.max(start[1], end[1]);
  return [minLon, minLat, maxLon, maxLat];
}

function formatBbox(bbox: BboxTuple | null): string {
  if (!bbox) {
    return "선택된 영역 없음";
  }
  return bbox.map((value) => value.toFixed(6)).join(", ");
}

function FitToValue({ value }: { value: BboxTuple | null }) {
  const map = useMap();

  useEffect(() => {
    if (!value) {
      return;
    }
    map.fitBounds(bboxToBounds(value), { padding: [24, 24], maxZoom: 14 });
  }, [map, value]);

  return null;
}

function DragSelectionLayer({
  modifierPressed,
  onDraft,
  onCommit
}: {
  modifierPressed: boolean;
  onDraft: (bbox: BboxTuple | null) => void;
  onCommit: (bbox: BboxTuple) => void;
}) {
  const map = useMap();
  const [start, setStart] = useState<LatLngTuple | null>(null);

  useEffect(() => {
    return () => {
      map.dragging.enable();
    };
  }, [map]);

  useMapEvents({
    mousedown: (event) => {
      const nativeEvent = event.originalEvent as MouseEvent;
      if (!(nativeEvent.shiftKey || nativeEvent.ctrlKey)) {
        return;
      }
      const dragStart: LatLngTuple = [event.latlng.lat, event.latlng.lng];
      setStart(dragStart);
      onDraft(pointsToBbox(dragStart, dragStart));
      map.dragging.disable();
    },
    mousemove: (event) => {
      if (!start) {
        return;
      }
      onDraft(pointsToBbox(start, [event.latlng.lat, event.latlng.lng]));
    },
    mouseup: (event) => {
      if (!start) {
        return;
      }
      const nextBbox = pointsToBbox(start, [event.latlng.lat, event.latlng.lng]);
      setStart(null);
      onDraft(null);
      map.dragging.enable();
      onCommit(nextBbox);
    }
  });

  useEffect(() => {
    if (start && !modifierPressed) {
      setStart(null);
      onDraft(null);
      map.dragging.enable();
    }
  }, [modifierPressed, map, onDraft, start]);

  return null;
}

export function WfsBboxPicker({ value, onChange }: WfsBboxPickerProps) {
  const [draftBbox, setDraftBbox] = useState<BboxTuple | null>(null);
  const [modifierPressed, setModifierPressed] = useState(false);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      setModifierPressed(event.shiftKey || event.ctrlKey);
    };
    const onKeyUp = (event: KeyboardEvent) => {
      setModifierPressed(event.shiftKey || event.ctrlKey);
    };
    const onBlur = () => setModifierPressed(false);

    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    window.addEventListener("blur", onBlur);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
      window.removeEventListener("blur", onBlur);
    };
  }, []);

  const displayedBbox = useMemo(() => draftBbox ?? value, [draftBbox, value]);

  return (
    <div className="wfs-bbox-picker">
      <div className="wfs-bbox-help">
        <span>영역 지정: Shift 또는 Ctrl + 마우스 드래그</span>
        <span>기본 동작: 지도 이동/확대/축소</span>
      </div>
      <div className="wfs-bbox-coords">
        <strong>BBOX (minLon, minLat, maxLon, maxLat):</strong>
        <code>{formatBbox(value)}</code>
      </div>
      <MapContainer
        center={[37.5665, 126.978]}
        zoom={7}
        className={`wfs-bbox-map ${modifierPressed ? "selection-mode" : ""}`}
        boxZoom={false}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <FitToValue value={value} />
        <DragSelectionLayer
          modifierPressed={modifierPressed}
          onDraft={setDraftBbox}
          onCommit={(bbox) => {
            setDraftBbox(null);
            onChange(bbox);
          }}
        />
        {displayedBbox ? (
          <Rectangle
            bounds={bboxToBounds(displayedBbox)}
            pathOptions={{ color: "#2f6f5e", weight: 2, fillColor: "#6e9186", fillOpacity: 0.18 }}
          />
        ) : null}
      </MapContainer>
    </div>
  );
}
