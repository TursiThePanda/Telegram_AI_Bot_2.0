# src/services/monitoring.py
"""
Service module for monitoring application performance and system health.
"""
import time
import json
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, Optional, List

import psutil
try:
    import GPUtil
    GPU_AVAILABLE = True
except ImportError:
    GPU_AVAILABLE = False

logger = logging.getLogger(__name__)

# --- Performance Monitoring ---
@dataclass
class RequestMetrics:
    request_id: str
    start_time: float
    user_id: Optional[int]
    request_type: str
    end_time: Optional[float] = None
    success: bool = True
    queue_wait_time: Optional[float] = None

    @property
    def response_time(self) -> Optional[float]:
        return self.end_time - self.start_time if self.end_time else None

class _PerformanceMonitor:
    def __init__(self):
        # Changed request_history to a dict for O(1) lookup during end_request
        self.active_requests: Dict[str, RequestMetrics] = {} 
        # Keep a deque for a fixed-size history of completed requests
        self.completed_request_history: Deque[RequestMetrics] = deque(maxlen=1000)
        self.start_time: float = time.time()

    def start_request(self, user_id: int, request_type: str) -> str:
        request_id = f"{int(time.time() * 1000)}_{user_id}"
        metrics = RequestMetrics(request_id, time.time(), user_id, request_type)
        self.active_requests[request_id] = metrics # Add to active requests
        return request_id

    def end_request(self, request_id: str, success: bool, queue_wait_time: float = 0):
        metrics = self.active_requests.pop(request_id, None) # Remove from active requests
        if metrics:
            metrics.end_time = time.time()
            metrics.success = success
            metrics.queue_wait_time = queue_wait_time
            self.completed_request_history.append(metrics) # Add to completed history
        else:
            logger.warning(f"Attempted to end request {request_id} which was not found or already ended.")

    # Added method to get overall stats, assuming it aggregates from completed_request_history
    def get_overall_stats(self) -> Dict[str, Any]:
        uptime_seconds = time.time() - self.start_time
        completed_requests = len(self.completed_request_history)
        successful_requests = sum(1 for m in self.completed_request_history if m.success)
        
        total_response_time = sum(m.response_time for m in self.completed_request_history if m.response_time is not None)
        average_response_time = total_response_time / completed_requests if completed_requests > 0 else 0

        success_rate = successful_requests / completed_requests if completed_requests > 0 else 1.0

        # Basic active users - counting unique user_ids in the last hour
        one_hour_ago = time.time() - 3600
        active_users_1h = len(set(m.user_id for m in self.completed_request_history if m.end_time and m.end_time > one_hour_ago and m.user_id is not None))
        
        # Simple total users seen (could be more robust with a persistent set)
        total_users_seen = len(set(m.user_id for m in self.completed_request_history if m.user_id is not None))


        return {
            'uptime_seconds': uptime_seconds,
            'completed_requests': completed_requests,
            'success_rate': success_rate,
            'average_response_time': average_response_time,
            'active_users_1h': active_users_1h,
            'total_users_seen': total_users_seen
        }


    async def export_report(self, filepath: str):
        logger.info(f"Exporting performance report to {filepath}...")
        try:
            # Export data from completed_request_history
            data = [m.__dict__ for m in self.completed_request_history if m.end_time]
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, default=str)
            logger.info(f"Performance report exported to {filepath}.")
        except Exception as e:
            logger.error(f"Failed to export performance report to {filepath}: {e}", exc_info=True)


# --- System Monitoring ---
class _SystemMonitor:
    def get_metrics(self) -> Dict[str, Any]:
        metrics = {
            'cpu_load': psutil.cpu_percent(interval=None),
            'memory_percent': psutil.virtual_memory().percent,
            'gpu_load': None,
            'gpu_temp': None
        }
        if GPU_AVAILABLE:
            try:
                # Assuming GPUtil.getGPUs() returns a list and we care about the first one
                gpus = GPUtil.getGPUs()
                if gpus:
                    gpu = gpus[0]
                    metrics.update({'gpu_load': gpu.load * 100, 'gpu_temp': gpu.temperature})
                else:
                    logger.debug("No GPUs detected by GPUtil.")
            except Exception as e: # Catch specific GPUtil errors if possible, or log broadly
                logger.warning(f"Failed to get GPU metrics using GPUtil: {e}", exc_info=True)
        return metrics

# --- Public Interface ---
performance_monitor = _PerformanceMonitor()
system_monitor = _SystemMonitor()

async def export_performance_report(filepath: str):
    await performance_monitor.export_report(filepath)

def get_system_metrics() -> Dict[str, Any]:
    return system_monitor.get_metrics()