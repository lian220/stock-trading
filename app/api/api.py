from fastapi import APIRouter
from app.api.routes.stock_recommendations import router as stock_recommendations_router
from app.api.routes.economic import router as economic_router
from app.api.routes.balance import router as balance_router
from app.api.routes.stocks import router as stocks_router
from app.api.routes.users import router as users_router
from app.api.routes.auto_trading import router as auto_trading_router
from app.api.routes.colab import router as colab_router
from app.api.routes.gcs_upload import router as gcs_upload_router

# 메인 API 라우터 생성
api_router = APIRouter()

# 모든 라우터 등록
api_router.include_router(stock_recommendations_router, prefix="/stocks", tags=["주식 추천"])
api_router.include_router(economic_router, prefix="/economic", tags=["경제 데이터"])
api_router.include_router(balance_router, prefix="/balance", tags=["잔액"])
api_router.include_router(stocks_router, prefix="/stocks", tags=["주식"])
api_router.include_router(users_router, prefix="/users", tags=["사용자"])
api_router.include_router(auto_trading_router, prefix="/auto-trading", tags=["자동매매"])
api_router.include_router(colab_router, prefix="/colab", tags=["Colab/Vertex AI"])
api_router.include_router(gcs_upload_router, prefix="/gcs", tags=["GCS 업로드"])