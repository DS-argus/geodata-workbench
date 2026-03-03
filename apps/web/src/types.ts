export type ListItem = {
  file_id: number;
  id: number;
  name: string;
  format: string;
  path: string;
  abs_path: string;
  size_bytes: number;
  created_at: string;
  crs?: string;
  raw_name?: string;
  total_rows?: number;
  display_name?: string;
  source_type?: "local_convert" | "wfs" | "unknown";
  filter_summary?: string;
  filter_detail_text?: string;
  conversion_status?: string;
  conversion_output_file_id?: number | null;
  conversion_output_name?: string;
  conversion_output_size?: number;
  conversion_output_rows?: number;
  conversion_error?: string;
};

export type PagedResponse<T> = {
  items: T[];
  total_items: number;
  total_pages: number;
  page: number;
  page_size: number;
};

export type ConvertOption = {
  file_id: number;
  name: string;
  abs_path: string;
  format: string;
  id: number;
  label: string;
};

export type WfsLayer = {
  key: string;
  display_name: string;
  typename: string;
  catalog_name: string;
  default_bbox_split: number;
  default_filters: WfsFilter[];
  columns: Array<{ name: string; name_ko: string }>;
};

export type WfsFilter = {
  type: "EQ" | "LIKE" | "BBOX";
  join_with_prev?: "AND" | "OR";
  column?: string;
  value?: string;
  geom_column?: string;
  bbox?: [number, number, number, number] | number[];
};
