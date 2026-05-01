from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import logging
from manual import ManualInvestigator

# 設定 Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = FastAPI(title="多模態毒品交易防治系統 - API 介面")

class CrawlRequest(BaseModel):
    url: str

@app.post("/api/crawl")
async def start_crawl(request: CrawlRequest):
    logging.info(f"API 手動查詢請求: {request.url}")
    
    # 單次請求單次初始化，避免任何資源共用衝突
    investigator = ManualInvestigator()
    result = await investigator.process_query(request.url)
    
    if result.get("threat_tier") == "SKIP" and "error_message" in result.get("crawler_data", {}):
        raise HTTPException(status_code=500, detail=result["crawler_data"]["error_message"])
        
    return {
        "status": "success",
        "msg": "深度探測與三合一分析完成",
        "data": {
            "target_url": request.url,
            **result
        }
    }

@app.get("/")
def read_root():
    return {
        "msg": "爬蟲系統架構 - 獨立查詢 API",
        "architecture": "Decoupled Single-Shot Investigator"
    }
