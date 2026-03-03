import axios from "axios";
import type { ConvertOption, ListItem, PagedResponse, WfsFilter, WfsLayer } from "./types";

const api = axios.create({ baseURL: "/api" });

export const fetchUploads = async (params: {
  page: number;
  pageSize: number;
  query: string;
  sortBy?: string;
  sortDir?: "asc" | "desc";
}): Promise<PagedResponse<ListItem>> => {
  const { data } = await api.get<PagedResponse<ListItem>>("/uploads", {
    params: {
      page: params.page,
      page_size: params.pageSize,
      query: params.query,
      sort_by: params.sortBy,
      sort_dir: params.sortDir
    }
  });
  return data;
};

export const createUploads = async (payload: {
  files: File[];
  relativePaths: string[];
  displayNames: string[];
  outputFormat: "geoparquet" | "gpkg";
}) => {
  const form = new FormData();
  payload.files.forEach((file) => form.append("files", file));
  payload.relativePaths.forEach((value) => form.append("relative_paths", value));
  payload.displayNames.forEach((value) => form.append("display_names", value));
  form.append("output_format", payload.outputFormat);
  const { data } = await api.post("/uploads", form, {
    headers: { "Content-Type": "multipart/form-data" }
  });
  return data as {
    saved_count: number;
    file_ids: number[];
    success_items: Array<{
      file_id: number;
      output_file_id?: number;
      name?: string;
    }>;
    failed_items: Array<{
      name: string;
      message?: string;
      user_message?: string;
    }>;
  };
};

export const deleteUpload = async (fileId: number) => {
  await api.delete(`/uploads/${fileId}`);
};

export const fetchConvertOptions = async (): Promise<ConvertOption[]> => {
  const { data } = await api.get<{ items: ConvertOption[] }>("/convert/options");
  return data.items;
};

export const fetchConvertInputColumns = async (
  fileId: number
): Promise<{
  columns: string[];
  sample_rows: Record<string, unknown>[];
  numeric_ranges: Record<string, { min: number; max: number; count: number }>;
  suggested_lat?: string | null;
  suggested_lon?: string | null;
  lat_reference: { min: number; max: number };
  lon_reference: { min: number; max: number };
}> => {
  const { data } = await api.get(`/convert/options/${fileId}/columns`);
  return data;
};

export const inspectTabularUpload = async (
  file: File
): Promise<{
  columns: string[];
  sample_rows: Record<string, unknown>[];
  numeric_ranges: Record<string, { min: number; max: number; count: number }>;
  suggested_lat?: string | null;
  suggested_lon?: string | null;
  lat_reference: { min: number; max: number };
  lon_reference: { min: number; max: number };
}> => {
  const form = new FormData();
  form.append("file", file);
  const { data } = await api.post("/uploads/tabular/inspect", form, {
    headers: { "Content-Type": "multipart/form-data" }
  });
  return data;
};

export const submitTabularUpload = async (
  payload: {
    file: File;
    displayName: string;
    output_format: "geoparquet" | "gpkg";
    csv_lat_col: string;
    csv_lon_col: string;
    csv_input_crs: string;
  }
): Promise<{ ok: boolean; output: Record<string, unknown> }> => {
  const form = new FormData();
  form.append("file", payload.file);
  form.append("display_name", payload.displayName);
  form.append("output_format", payload.output_format);
  form.append("csv_lat_col", payload.csv_lat_col);
  form.append("csv_lon_col", payload.csv_lon_col);
  form.append("csv_input_crs", payload.csv_input_crs);
  const { data } = await api.post("/uploads/tabular/submit", form, {
    headers: { "Content-Type": "multipart/form-data" }
  });
  return data;
};

export const runConversion = async (payload: {
  input_file_id: number;
  output_format: string;
  crs_handling: "keep" | "transform";
  target_crs?: string;
  csv_lat_col?: string;
  csv_lon_col?: string;
  csv_input_crs?: string;
}) => {
  const { data } = await api.post("/conversions", payload);
  return data;
};

export const startConversion = async (payload: {
  input_file_id: number;
  output_format: string;
  crs_handling: "keep" | "transform";
  target_crs?: string;
  csv_lat_col?: string;
  csv_lon_col?: string;
  csv_input_crs?: string;
}): Promise<{ job_id: number }> => {
  const { data } = await api.post<{ job_id: number }>("/conversions/start", payload);
  return data;
};

export const fetchConversionJob = async (
  jobId: number
): Promise<{ job_id: number; status: string; error_message?: string | null; output_file_id?: number | null }> => {
  const { data } = await api.get(`/conversions/jobs/${jobId}`);
  return data;
};

export const cancelConversionJob = async (jobId: number): Promise<{ ok: boolean; status?: string }> => {
  const { data } = await api.post(`/conversions/jobs/${jobId}/cancel`);
  return data;
};

export const fetchConversions = async (params: {
  page: number;
  pageSize: number;
  query: string;
}): Promise<PagedResponse<ListItem>> => {
  const { data } = await api.get<PagedResponse<ListItem>>("/conversions", {
    params: {
      page: params.page,
      page_size: params.pageSize,
      query: params.query
    }
  });
  return data;
};

export const deleteConversion = async (fileId: number) => {
  await api.delete(`/conversions/${fileId}`);
};

export const fetchDatasets = async (): Promise<
  Array<{
    file_id: number;
    name: string;
    display_name: string;
    total_rows: number;
    abs_path: string;
    crs: string;
    format: string;
    source_type: "local_convert" | "wfs" | "unknown";
  }>
> => {
  const { data } = await api.get<{ items: Array<any> }>("/datasets");
  return data.items;
};

export const fetchDatasetPreview = async (fileId: number, limit: number) => {
  const { data } = await api.get<{ columns: string[]; rows: Record<string, unknown>[] }>(
    `/datasets/${fileId}/preview`,
    { params: { limit } }
  );
  return data;
};

export const fetchDatasetGeojson = async (fileId: number, limit: number) => {
  const { data } = await api.get(`/datasets/${fileId}/geojson`, { params: { limit } });
  return data as GeoJSON.FeatureCollection;
};

export const fetchWfsConfig = async (): Promise<{ provider: string; has_api_key: boolean; key_masked: string }> => {
  const { data } = await api.get("/wfs/config");
  return data;
};

export const updateWfsApiKey = async (apiKey: string): Promise<{ ok: boolean; key_masked: string }> => {
  const { data } = await api.put("/wfs/config/api-key", { api_key: apiKey });
  return data;
};

export const fetchWfsLayers = async (): Promise<WfsLayer[]> => {
  const { data } = await api.get<{ items: WfsLayer[] }>("/wfs/layers");
  return data.items;
};

export const startWfsCollection = async (payload: {
  layer_key: string;
  output_format: "geoparquet" | "gpkg";
  srs_name: string;
  filters?: WfsFilter[];
  bbox_split?: number;
  max_features?: number;
}): Promise<{ job_id: number }> => {
  const { data } = await api.post<{ job_id: number }>("/wfs/collections/start", payload);
  return data;
};

export const fetchWfsJob = async (
  jobId: number
): Promise<{
  job_id: number;
  status: string;
  error_message?: string | null;
  output_file_id?: number | null;
  progress_percent?: number;
  progress_message?: string | null;
}> => {
  const { data } = await api.get(`/wfs/jobs/${jobId}`);
  return data;
};

export const cancelWfsJob = async (jobId: number): Promise<{ ok: boolean; status?: string }> => {
  const { data } = await api.post(`/wfs/jobs/${jobId}/cancel`);
  return data;
};

export const fetchWfsCollections = async (params: {
  page: number;
  pageSize: number;
  query: string;
  sortBy?: string;
  sortDir?: "asc" | "desc";
}): Promise<PagedResponse<ListItem>> => {
  const { data } = await api.get<PagedResponse<ListItem>>("/wfs/collections", {
    params: {
      page: params.page,
      page_size: params.pageSize,
      query: params.query,
      sort_by: params.sortBy,
      sort_dir: params.sortDir
    }
  });
  return data;
};

export const deleteWfsCollection = async (fileId: number) => {
  await api.delete(`/wfs/collections/${fileId}`);
};
