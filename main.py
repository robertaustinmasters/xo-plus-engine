import os
import uvicorn
from fastapi import FastAPI, APIRouter, Depends, HTTPException, BackgroundTasks, Header
import stripe
import httpx
from datetime import datetime, timezone

app = FastAPI(
    title="U4U Universal Bridge Server - Omega Edition",
    version="4.1.0",
    description="Compliant routing engine for Stripe treasury sweeps and mesh telemetry."
)
router = APIRouter(prefix="/api/v1/treasury", tags=["Omega Sweep Execution"])

# Sovereign Target & Compliance Parameters
VENMO_OFFRAMP_TARGET = "@Skinny3388"
COMPLIANT_TRANSACTION_LIMIT = 3000.00

# Production Credentials via Environment Variables (Render Secrets)
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_DESTINATION_ACCOUNT = os.getenv("STRIPE_DESTINATION_ACCOUNT", "acct_1TSdaoQbxBQqicTC")
REVCAST_API_URL = "https://api.revcast.com/v1/telemetry/events"
REVCAST_API_KEY = os.getenv("REVCAST_API_KEY", "YOUR_REVCAST_INTEGRATION_KEY")
OPERATOR_TOKEN = os.getenv("OPERATOR_JWT_TOKEN", "YOUR_OPERATOR_TOKEN")

async def broadcast_to_revcast(event_type: str, data: dict):
    """Pipes background telemetry to the Revcast engine."""
    headers = {"Authorization": f"Bearer {REVCAST_API_KEY}", "Content-Type": "application/json"}
    payload = {"timestamp": datetime.now(timezone.utc).isoformat(), "event_type": event_type, "properties": data}
    async with httpx.AsyncClient() as client:
        try:
            await client.post(REVCAST_API_URL, json=payload, headers=headers)
        except Exception:
            pass

async def auth_guard(authorization: str = Header(...)):
    """Verifies the dynamic operator token."""
    expected_header = f"Bearer {OPERATOR_TOKEN}"
    if authorization != expected_header:
        raise HTTPException(status_code=401, detail="Unauthorized Operator")
    return {"canonical_user_id": "usr_77492B_MASTERS"}

@router.get("/")
async def health_check():
    """Uptime health check endpoint."""
    return {
        "status": "online",
        "system": "U4U Universal Bridge Server - Omega Edition",
        "destination_account": STRIPE_DESTINATION_ACCOUNT,
        "batch_limit": COMPLIANT_TRANSACTION_LIMIT,
        "offramp": VENMO_OFFRAMP_TARGET
    }

@router.post("/execute-compliant-sweep")
async def execute_compliant_sweep(
    requested_amount: float,
    background_tasks: BackgroundTasks,
    session: dict = Depends(auth_guard)
):
    """
    Executes a compliant transfer request constrained by the $3,000 transaction limit.
    """
    if requested_amount <= 0:
        raise HTTPException(status_code=400, detail="Requested amount must be greater than zero.")
        
    processing_amount = min(requested_amount, COMPLIANT_TRANSACTION_LIMIT)
    
    try:
        # Transmit transfer payload to Stripe API
        stripe.Transfer.create(
            amount=int(processing_amount * 100),  # Amount in cents
            currency="usd",
            destination=STRIPE_DESTINATION_ACCOUNT,
            description=f"Compliant Mesh Transfer to {VENMO_OFFRAMP_TARGET}"
        )
        
        # Log execution event to Revcast telemetry
        background_tasks.add_task(
            broadcast_to_revcast,
            event_type="compliant_sweep_executed",
            data={
                "requested_amount": requested_amount,
                "processed_amount": processing_amount,
                "destination": VENMO_OFFRAMP_TARGET,
                "stripe_account": STRIPE_DESTINATION_ACCOUNT,
                "user_id": session["canonical_user_id"]
            }
        )
            
        return {
            "status": "request_transmitted",
            "processed_amount": processing_amount,
            "destination_target": VENMO_OFFRAMP_TARGET,
            "stripe_connected_account": STRIPE_DESTINATION_ACCOUNT,
            "message": f"Successfully transmitted routing request for ${processing_amount:,.2f}. Balance must be processed in subsequent batches."
        }
        
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gateway transmission failure: {str(e)}")

app.include_router(router)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
