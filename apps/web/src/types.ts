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
