
from sqlalchemy import func
from fastapi import Query
from datetime import datetime, timedelta
import asyncio
from fastapi.responses import JSONResponse
from sqlalchemy import func
from app.models import APIMetric, Base
from app.database import SessionLocal, engine, test_connection
import time
from fastapi import Query
from fastapi import Request
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError


app = FastAPI(
    title="API Performance Monitoring Dashboard",
    description="Manage and monitor API performance",
    version="1.0.0"
)
Base.metadata.create_all(bind=engine)
@app.middleware("http")
async def monitor_api_requests(request: Request, call_next):
    # Skip monitoring endpoints to avoid counting dashboard polling
    if request.url.path.startswith("/metrics"): 
        return await call_next(request)
    start_time = time.perf_counter()

    response = await call_next(request)

    # Calculate response time in milliseconds
    process_time = (time.perf_counter() - start_time) * 1000

    # Save request details to PostgreSQL
    db = SessionLocal()

    try:
        metric = APIMetric(
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            response_time_ms=round(process_time, 2)
        )

        db.add(metric)
        db.commit()

    except Exception as error:
        db.rollback()
        print(f"Error saving API metric: {error}")

    finally:
        db.close()

    # Show performance information in terminal
    print(
        f"{request.method} {request.url.path} "
        f"| Status: {response.status_code} "
        f"| Time: {process_time:.2f} ms"
    )

    return response

# Request data for adding an API
class APIInput(BaseModel):
    name: str
    url: HttpUrl


# Home endpoint
@app.get("/")
def home():
    return {
        "message": "API Monitoring Dashboard is running!"
    }


# Check database connection
@app.get("/health/db")
def database_health():
    try:
        test_connection()
        return {
            "database": "connected",
            "status": "healthy"
        }
    except SQLAlchemyError:
        raise HTTPException(
            status_code=503,
            detail="Database connection failed"
        )


# Add a new API
@app.post("/apis", status_code=201)
def add_api(api: APIInput):
    try:
        with engine.begin() as connection:
            result = connection.execute(
                text("""
                    INSERT INTO monitored_apis (name, url)
                    VALUES (:name, :url)
                    RETURNING id, name, url, is_active, created_at
                """),
                {
                    "name": api.name,
                    "url": str(api.url)
                }
            )

            return dict(result.mappings().one())

    except SQLAlchemyError:
        raise HTTPException(
            status_code=500,
            detail="Could not add API. Check the database table."
        )


# Get all monitored APIs
@app.get("/apis")
def get_apis():
    try:
        with engine.connect() as connection:
            result = connection.execute(
                text("""
                    SELECT id, name, url, is_active, created_at
                    FROM monitored_apis
                    ORDER BY id
                """)
            )

            return [dict(row) for row in result.mappings().all()]

    except SQLAlchemyError:
        raise HTTPException(
            status_code=500,
            detail="Could not retrieve APIs."
        )


# Get one API by ID
@app.get("/apis/{api_id}")
def get_api(api_id: int):
    try:
        with engine.connect() as connection:
            result = connection.execute(
                text("""
                    SELECT id, name, url, is_active, created_at
                    FROM monitored_apis
                    WHERE id = :api_id
                """),
                {"api_id": api_id}
            )

            api = result.mappings().first()

            if api is None:
                raise HTTPException(
                    status_code=404,
                    detail="API not found"
                )

            return dict(api)

    except SQLAlchemyError:
        raise HTTPException(
            status_code=500,
            detail="Could not retrieve API."
        )


# Activate or deactivate an API
@app.patch("/apis/{api_id}/status")
def update_api_status(api_id: int, is_active: bool):
    try:
        with engine.begin() as connection:
            result = connection.execute(
                text("""
                    UPDATE monitored_apis
                    SET is_active = :is_active
                    WHERE id = :api_id
                    RETURNING id, name, url, is_active
                """),
                {
                    "api_id": api_id,
                    "is_active": is_active
                }
            )

            api = result.mappings().first()

            if api is None:
                raise HTTPException(
                    status_code=404,
                    detail="API not found"
                )

            return dict(api)

    except SQLAlchemyError:
        raise HTTPException(
            status_code=500,
            detail="Could not update API status."
        )
@app.get("/metrics")
def get_metrics(limit: int = Query(default=100, ge=1, le=1000)):
    db = SessionLocal()

    try:
        metrics = (
            db.query(APIMetric)
            .order_by(APIMetric.created_at.desc())
            .limit(limit)
            .all()
        )

        return [
            {
                "id": metric.id,
                "method": metric.method,
                "path": metric.path,
                "status_code": metric.status_code,
                "response_time_ms": metric.response_time_ms,
                "created_at": metric.created_at,
            }
            for metric in metrics
        ]

    finally:
        db.close()
@app.get("/metrics/summary")
def get_metrics_summary():
    db = SessionLocal()

    try:
        # Total number of requests
        total_requests = db.query(APIMetric).count()

        # Average response time
        average_time = (
            db.query(func.avg(APIMetric.response_time_ms))
            .scalar()
        )

        # Count requests with errors (HTTP 4xx or 5xx)
        error_count = (
            db.query(APIMetric)
            .filter(APIMetric.status_code >= 400)
            .count()
        )

        # Calculate error rate
        error_rate = (
            (error_count / total_requests) * 100
            if total_requests > 0
            else 0
        )

        return {
            "total_requests": total_requests,
            "average_response_time_ms": round(average_time or 0, 2),
            "error_count": error_count,
            "error_rate_percent": round(error_rate, 2),
        }

    finally:
        db.close()
@app.get("/metrics/slow")
def get_slow_requests(
    threshold_ms: float = Query(default=500, gt=0),
    limit: int = Query(default=100, ge=1, le=1000)
):
    db = SessionLocal()

    try:
        slow_requests = (
            db.query(APIMetric)
            .filter(APIMetric.response_time_ms >= threshold_ms)
            .order_by(APIMetric.response_time_ms.desc())
            .limit(limit)
            .all()
        )

        return {
            "threshold_ms": threshold_ms,
            "slow_request_count": len(slow_requests),
            "slow_requests": [
                {
                    "id": metric.id,
                    "method": metric.method,
                    "path": metric.path,
                    "status_code": metric.status_code,
                    "response_time_ms": metric.response_time_ms,
                    "created_at": metric.created_at,
                }
                for metric in slow_requests
            ],
        }

    finally:
        db.close()        
@app.get("/metrics/overview")
def get_metrics_overview():
    db = SessionLocal()

    try:
        total_requests = db.query(APIMetric).count()

        average_time = (
            db.query(func.avg(APIMetric.response_time_ms))
            .scalar()
        ) or 0

        error_count = (
            db.query(APIMetric)
            .filter(APIMetric.status_code >= 400)
            .count()
        )

        slow_count = (
            db.query(APIMetric)
            .filter(APIMetric.response_time_ms >= 500)
            .count()
        )

        error_rate = (
            (error_count / total_requests) * 100
            if total_requests > 0
            else 0
        )

        average_time = round(average_time, 2)
        error_rate = round(error_rate, 2)

        # Simple, configurable health rules
        if error_rate >= 20 or average_time >= 1000:
            health_status = "unhealthy"
        elif error_rate >= 5 or average_time >= 500:
            health_status = "degraded"
        else:
            health_status = "healthy"

        return {
            "health_status": health_status,
            "total_requests": total_requests,
            "average_response_time_ms": average_time,
            "error_count": error_count,
            "error_rate_percent": error_rate,
            "slow_request_count": slow_count,
        }

    finally:
        db.close()
@app.get("/demo/fast")
async def demo_fast():
    return {"message": "Fast response"}


@app.get("/demo/slow")
async def demo_slow():
    await asyncio.sleep(1)
    return {"message": "Simulated slow response"}


@app.get("/demo/error")
async def demo_error():
    return JSONResponse(
        status_code=500,
        content={"message": "Simulated test error"}
    )

@app.get("/metrics/advanced")
def advanced_metrics(
    window_minutes: int = Query(default=5, ge=1, le=1440)
):
    db = SessionLocal()

    try:
        cutoff = datetime.utcnow() - timedelta(
            minutes=window_minutes
        )

        metrics = (
            db.query(APIMetric)
            .filter(APIMetric.created_at >= cutoff)
            .all()
        )

        total = len(metrics)

        if total == 0:
            return {
                "window_minutes": window_minutes,
                "total_requests": 0,
                "p95_response_time_ms": 0,
                "requests_per_second": 0,
                "endpoint_errors": []
            }

        response_times = sorted(
            float(metric.response_time_ms)
            for metric in metrics
        )

        # Nearest-rank P95 calculation
        p95_index = max(
            0,
            int(0.95 * total + 0.999999) - 1
        )
        p95 = response_times[p95_index]

        # Average request throughput over the selected window
        rps = total / (window_minutes * 60)

        endpoint_stats = {}

        for metric in metrics:
            key = (metric.method, metric.path)

            if key not in endpoint_stats:
                endpoint_stats[key] = {
                    "method": metric.method,
                    "path": metric.path,
                    "total": 0,
                    "errors": 0
                }

            endpoint_stats[key]["total"] += 1

            if metric.status_code >= 400:
                endpoint_stats[key]["errors"] += 1

        endpoint_errors = []

        for stats in endpoint_stats.values():
            errors = stats["errors"]
            count = stats["total"]

            endpoint_errors.append({
                "method": stats["method"],
                "path": stats["path"],
                "total_requests": count,
                "error_count": errors,
                "error_rate_percent": round(
                    errors / count * 100, 2
                )
            })

        endpoint_errors.sort(
            key=lambda item: item["error_rate_percent"],
            reverse=True
        )

        return {
            "window_minutes": window_minutes,
            "total_requests": total,
            "p95_response_time_ms": round(p95, 2),
            "requests_per_second": round(rps, 4),
            "endpoint_errors": endpoint_errors
        }

    finally:
        db.close()
