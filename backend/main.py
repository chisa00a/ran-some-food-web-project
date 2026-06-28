from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests

app = FastAPI(title="Food Map Proxy API")

# ตั้งค่า CORS เพื่อให้ Frontend (ที่อยู่คนละ Port หรือคนละ Domain) ยิงหาหลังบ้านได้
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # เวลาขึ้นระบบจริงค่อยเปลี่ยนเป็น URL ของ Frontend เพื่อความปลอดภัย
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# โครงสร้างข้อมูลที่รับมาจากหน้าเว็บ
class SearchPayload(BaseModel):
    lat: float
    lng: float
    keyword: str

@app.post("/api/search-food")
async def search_food(payload: SearchPayload):
    # รัศมีการค้นหา (เมตร) เช่น 1500 เมตร = 1.5 กิโลเมตร
    radius = 1500 
    
    # คำสั่ง Overpass QL ค้นหาสถานที่ประเภท ร้านอาหาร, ศูนย์อาหาร, คาเฟ่, ร้านฟาสต์ฟู้ด รอบพิกัดตัวเรา
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
        # ยิงคำขอไปที่ OpenStreetMap Server
        response = requests.post(overpass_url, data={"data": overpass_query})
        response.raise_for_status()
        raw_data = response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Overpass API Connection Error: {str(e)}")

    # สกัดเอาเฉพาะข้อมูลพิกัดและชื่อร้านที่เราต้องการใช้งาน
    processed_restaurants = []
    # ดึงคีย์เวิร์ดที่สุ่มได้จากหน้าเว็บ เช่น "ก๋วยเตี๋ยว"
    search_keyword = payload.keyword.lower() 

    for element in raw_data.get("elements", []):
        lat = element.get("lat") or element.get("center", {}).get("lat")
        lng = element.get("lon") or element.get("center", {}).get("lon")
        tags = element.get("tags", {})
        
        name = tags.get("name", "ร้านอาหารไม่มีชื่อ")
        amenity_type = tags.get("amenity", "food")
        
        # --- เพิ่ม Logic การกรองข้อมูลตรงนี้ ---
        # 1. เช็คว่าชื่อเมนูที่สุ่มได้ อยู่ในชื่อร้านไหม? (เช่น สุ่มได้ก๋วยเตี๋ยว เจอร้าน "ก๋วยเตี๋ยวเรือคุณนัย")
        # 2. หรือถ้าเมนูยาวไป ให้เช็คคำบางคำ เช่น ถ้าสุ่มได้ "ข้าวมันไก่" ให้หาร้านที่มีคำว่า "ไก่" หรือ "ข้าว"
        is_match = search_keyword in name.lower()
        
        # (ออปชั่นเสริม) ถ้าอยากให้หาร้านเจอชัวร์ๆ แนะนำให้เตรียม mapping คำศัพท์ไว้ด้วย
        # แต่เบื้องต้นใช้การดัก keyword ในชื่อร้านแบบนี้ไปก่อนได้ครับ

        if lat and lng and is_match:
            processed_restaurants.append({
                "name": name,
                "lat": lat,
                "lng": lng,
                "type": amenity_type,
            })
            
    # ถ้าหาร้านที่ตรงเป๊ะไม่เจอเลย ให้ดึงร้านทั่วไปแถวนั้นมาแนะนำแทน (ป้องกันแผนที่ว่างเปล่า)
    if len(processed_restaurants) == 0:
        for element in raw_data.get("elements", [])[:5]: # ดึงมา 5 ร้านแก้ขัด
             tags = element.get("tags", {})
             if "name" in tags:
                 lat = element.get("lat") or element.get("center", {}).get("lat")
                 lng = element.get("lon") or element.get("center", {}).get("lon")
                 processed_restaurants.append({
                     "name": tags.get("name") + " (ร้านแนะนำแทน)",
                     "lat": lat, "lng": lng, "type": tags.get("amenity")
                 })

    return {
        "status": "success",
        "keyword": payload.keyword,
        "total_found": len(processed_restaurants),
        "restaurants": processed_restaurants
    }