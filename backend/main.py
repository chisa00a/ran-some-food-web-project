from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import requests
import os

app = FastAPI(title="Food Randomizer Local Server")

# เปิดสิทธิ์ CORS ให้เข้าถึงได้ทุกช่องทาง
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SearchPayload(BaseModel):
    lat: float
    lng: float
    keyword: str

# 🌟 ฟังก์ชันใหม่: สั่งให้ FastAPI เปิดหน้าเว็บ index.html ให้เราโดยตรง
@app.get("/")
async def get_frontend():
    # หาตำแหน่งของไฟล์ index.html ที่อยู่โฟลเดอร์ frontend ข้างๆ กัน
    frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html")
    if os.path.exists(frontend_path):
        return FileResponse(frontend_path)
    return {"error": "หาไฟล์ index.html ไม่เจอเพื่อน ลองเช็คโครงสร้างโฟลเดอร์ดูนะ"}

@app.post("/api/search-food")
async def search_food(payload: SearchPayload):
    radius = 2000  # ขยายรัศมีเป็น 2000 เมตร (2 กิโลเมตร) รอบตัวเรา จะได้เจอร้านเยอะขึ้น
    
    # คำสั่งดึงร้านอาหาร คาเฟ่ ศูนย์อาหาร รอบตัว
    overpass_query = f"""
    [out:json][timeout:30];
    (
      node["amenity"~"restaurant|food_court|cafe|fast_food"](around:{radius}, {payload.lat}, {payload.lng});
      way["amenity"~"restaurant|food_court|cafe|fast_food"](around:{radius}, {payload.lat}, {payload.lng});
    );
    out center;
    """
    
    overpass_url = "https://overpass-api.de/api/interpreter"
    
    try:
        response = requests.post(overpass_url, data={"data": overpass_query})
        response.raise_for_status()
        raw_data = response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ดึงข้อมูลแผนที่พลาด: {str(e)}")

    processed_restaurants = []
    search_keyword = payload.keyword.strip()
    
    # 🌟 ฟังก์ชันล็อกชนิดอาหาร: จับคู่คำค้นหาภาษาไทยให้ยืดหยุ่นขึ้น
    # เช่น ถ้าสุ่มได้ "ก๋วยเตี๋ยว" ให้พยายามหาร้านที่มีคำว่า "เตี๋ยว", "บะหมี่" หรือ "เส้น" ด้วย
    keywords_to_check = [search_keyword]
    if "ก๋วยเตี๋ยว" in search_keyword:
        keywords_to_check.extend(["เตี๋ยว", "บะหมี่", "ลูกชิ้น", "เส้น", "noodle"])
    elif "กะเพรา" in search_keyword:
        keywords_to_check.extend(["กะเพรา", "กระเพรา", "ตามสั่ง"])
    elif "ไก่" in search_keyword:
        keywords_to_check.extend(["ไก่", "chicken"])
    elif "ชาบู" in search_keyword or "หมูกระทะ" in search_keyword:
        keywords_to_check.extend(["ชาบู", "หมูกระทะ", "ปิ้งย่าง", "shabu"])
    elif "ส้มตำ" in search_keyword:
        keywords_to_check.extend(["ส้มตำ", "ลาบ", "อีสาน"])

    for element in raw_data.get("elements", []):
        lat = element.get("lat") or element.get("center", {}).get("lat")
        lng = element.get("lon") or element.get("center", {}).get("lon")
        tags = element.get("tags", {})
        name = tags.get("name", "")
        
        if not name:
            continue
            
        # ตรวจสอบว่าชื่อร้านมีคำที่ตรงหรือเกี่ยวข้องกับเมนูที่สุ่มได้ไหม
        is_match = any(kw.lower() in name.lower() for kw in keywords_to_check)
        
        if lat and lng and is_match:
            processed_restaurants.append({
                "name": name,
                "lat": lat,
                "lng": lng,
                "type": tags.get("amenity", "food"),
                "cuisine": tags.get("cuisine", "ทั่วไป")
            })
            
    # 💡 กรณีฉุกเฉิน: ถ้าแถวบ้านไม่มีร้านที่ตรงกับเมนูที่สุ่มได้เลยในระยะ 2 กม. 
    # ให้ดึงร้านอาหารทั่วไปใกล้ตัว 5 ร้านขึ้นมาแนะนำแทน แผนที่จะได้ไม่ว่างเปล่า
    if len(processed_restaurants) == 0:
        for element in raw_data.get("elements", [])[:5]:
            tags = element.get("tags", {})
            shop_name = tags.get("name")
            if shop_name:
                lat = element.get("lat") or element.get("center", {}).get("lat")
                lng = element.get("lon") or element.get("center", {}).get("lon")
                processed_restaurants.append({
                    "name": f"{shop_name} (แนะนำเพิ่มเติมใกล้คุณ)",
                    "lat": lat,
                    "lng": lng,
                    "type": tags.get("amenity", "food"),
                    "cuisine": tags.get("cuisine", "ทั่วไป")
                })

    return {
        "status": "success",
        "keyword": payload.keyword,
        "total_found": len(processed_restaurants),
        "restaurants": processed_restaurants
    }