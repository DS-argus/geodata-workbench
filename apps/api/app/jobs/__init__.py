from app.jobs.conversion import build_conversion_params, run_conversion_job
from app.jobs.runner import BackgroundJobRunner
from app.jobs.wfs import build_wfs_request_params, run_wfs_job


conversion_jobs = BackgroundJobRunner(thread_name_prefix="conversion-job")
wfs_jobs = BackgroundJobRunner(thread_name_prefix="wfs-job")


__all__ = [
    "build_conversion_params",
    "build_wfs_request_params",
    "conversion_jobs",
    "run_conversion_job",
    "run_wfs_job",
    "wfs_jobs",
]
