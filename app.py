from fastapi import FastAPI, HTTPException
from supabase import create_client, Client
from typing import List
from dotenv import load_dotenv
import os
# --- Supabase Connection ---\

load_dotenv("keys.env")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


from fastapi import FastAPI, HTTPException
from supabase import create_client, Client
from pydantic import BaseModel
from typing import List, Optional

from datetime import date 

app = FastAPI()


# --- Pydantic Models for Data Validation ---
class BookingCreate(BaseModel):
    slot_id: str
    customer_name: str
    phone_number: str
    email: Optional[str] = None
    guest_count: int


class InquiryCreate(BaseModel):
    customer_name: str
    phone_number: str
    email: Optional[str] = None
    event_type: str
    proposed_date: Optional[str] = None
    guest_count: Optional[int] = None
    requirements: Optional[str] = None


class CallLogCreate(BaseModel):
    customer_id: Optional[int]
    call_duration: int
    call_intent: str
    call_summary: str
    sentiment: str
    was_out_of_scope: bool
    was_escalated: bool
    notes: Optional[str] = None
    suspects_ai:bool

@app.get("/check-availability/", response_model=List[dict])
def check_availability(
    theme: Optional[str] = None, 
    date_str: Optional[str] = None, # Renamed to avoid conflict
    time: Optional[str] = None
):
    """
    Finds the top 3 soonest available slots based on optional filters,
    including an optional time.
    """
    try:
        query = supabase.table('Slots').select(
            'slot_id, room_theme, slot_date, slot_time'
        ).eq('status', 'Available')

        # Filter from today onwards if no specific date is given
        if not date_str:
            query = query.gte('slot_date', date.today().isoformat())
        else:
            query = query.eq('slot_date', date_str)
        
        # Add optional filters
        if theme:
            query = query.eq('room_theme', theme)
        if time:
            query = query.gte('slot_time', time) # gte = greater than or equal to

        # Sort and limit the results
        response = query.order('slot_date').order('slot_time').limit(5).execute()
        
        return response.data

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/create-booking/", response_model=dict)
def create_booking(booking_data: BookingCreate):
    """Creates a customer (if new) and a booking, then updates the slot status."""
    try:
        # 1. Check if the slot is still available
        slot_response = supabase.table("Slots").select("status").eq("slot_id", int(booking_data.slot_id)).single().execute()
        slot = slot_response.data

        if not slot or slot.get("status") != "Available":
            return {"error": "Slot not found or already booked", "details": slot}
        
        if booking_data.guest_count <= 0:
            return {"error": "Guest count must be a positive integer"}
        # 2. Find or create the customer
        customer_response = supabase.table("Customers").upsert({
            "phone_number": booking_data.phone_number,
            "customer_name": booking_data.customer_name,
            "email": booking_data.email
        },on_conflict="phone_number" ).execute()
        customer_id = customer_response.data[0]["customer_id"]

        # 3. Create the booking
        booking_response = supabase.table("bookings").insert({
            "slot_id": booking_data.slot_id,
            "customer_id": customer_id,
            "guest_count": booking_data.guest_count
        }).execute()
        booking_id = booking_response.data[0]["booking_id"]

        # 4. Update the slot status to 'booked'
        supabase.table("Slots").update({"status": "booked"}).eq("slot_id", booking_data.slot_id).execute()

        return {"status": "success", "booking_id": booking_id}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/create-inquiry/", response_model=dict)
def create_inquiry(inquiry_data: InquiryCreate):
    """Creates a customer (if new) and an event inquiry for sales follow-up."""
    try:
        # 1. Find or create the customer
        customer_response = supabase.table('Customers').upsert({
            'phone_number': inquiry_data.phone_number,
            'customer_name': inquiry_data.customer_name,
            'email': inquiry_data.email
        },on_conflict="phone_number" ).execute()
        customer_id = customer_response.data[0]['customer_id']

        # 2. Create the event inquiry
        inquiry_response = supabase.table('event_inquiries').insert({
            'customer_id': customer_id,
            'event_type': inquiry_data.event_type,
            'proposed_date': inquiry_data.proposed_date,
            'guest_count': inquiry_data.guest_count,
            'requirements': inquiry_data.requirements
        }).execute()
        inquiry_id = inquiry_response.data[0]['inquiry_id']

        return {"status": "success", "inquiry_id": inquiry_id}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/call_logs", response_model=dict)
def log_call(call_data: CallLogCreate):
    """Logs call details into the call_logs table."""
    try:
        data_dict = call_data.model_dump(exclude_none=True)

        # Insert into Supabase
        response = supabase.table("call_logs").insert(data_dict).execute()

        if not response.data:
            raise HTTPException(status_code=500, detail="Failed to insert call log")

        log_id = response.data[0].get("log_id")
        created_at = response.data[0].get("created_at")  # optional return

        return {"status": "success", "log_id": log_id, "created_at": created_at}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    


@app.get("/booking-details/", response_model=List[dict])
def get_booking_details(phone_number: str):
    """
    Retrieves future booking details for a customer based on their phone number.
    """
    try:
        # 1. Find the customer by their phone number
        customer_response = supabase.table("Customers").select("customer_id").eq("phone_number", phone_number).single().execute()
        
        print("DEBUG : ",customer_response.data)
        if not customer_response.data:
            return [] # Return an empty list if no customer is found
        
        customer_id = customer_response.data["customer_id"]

        print("DEBUG : Customer ID",customer_id)
        # 2. Find future bookings for that customer and get the related slot info
        today_str = date.today().isoformat()
        

        # --- TEMPORARY DEBUGGING CODE ---
        print(f"DEBUG: Searching for bookings with customer_id: {customer_id}")

        # Let's simplify the query to find ANY booking for this customer
        debug_response = supabase.table("bookings").select("*").eq("customer_id", customer_id).execute()

        print("DEBUG: Raw bookings found for this customer:", debug_response.data)
        # --- END OF DEBUGGING CODE ---
        bookings_response = supabase.table("bookings").select(
            "*, Slots!inner(*)"  # This fetches all booking columns and all related slot columns
        ).eq("customer_id", customer_id).gte("Slots.slot_date", today_str).execute()

        print("DEBUG : Bookings Response",bookings_response.data)
        return bookings_response.data

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
