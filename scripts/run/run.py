import uvicorn
import os
import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
# run.py가 scripts/run/에 있으므로 상위 두 단계가 프로젝트 루트
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

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