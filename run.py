import uvicorn
import os

if __name__ == "__main__":
    # 환경 변수로 reload 모드 제어 (기본값: False)
    # 개발 모드일 때만 reload 활성화하려면: export APP_ENV=development
    reload_mode = os.getenv("APP_ENV", "production") == "development"
    
    uvicorn.run(
        "app.main:app", 
        host="0.0.0.0", 
        port=8000, 
        reload=reload_mode,
        reload_dirs=["app"] if reload_mode else None,  # app 디렉토리만 감시
        access_log=False
    )