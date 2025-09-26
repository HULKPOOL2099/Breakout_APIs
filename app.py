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
    guest_count_estimate: Optional[int] = None
    requirements: Optional[str] = None


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
        slot_response = supabase.table('Slots').select('status').eq('slot_id', booking_data.slot_id).single().execute()
        if slot_response.data['status'] != 'available':
            raise HTTPException(status_code=409, detail="This slot is no longer available.")

        # 2. Find or create the customer (Upsert)
        customer_response = supabase.table('Customers').upsert({
            'phone_number': booking_data.phone_number,
            'customer_name': booking_data.customer_name,
            'email': booking_data.email
        }).execute()
        customer_id = customer_response.data[0]['customer_id']

        # 3. Create the booking
        booking_response = supabase.table('bookings').insert({
            'slot_id': booking_data.slot_id,
            'customer_id': customer_id,
            'guest_count': booking_data.guest_count
        }).execute()
        booking_id = booking_response.data[0]['booking_id']

        # 4. Update the slot status to 'booked'
        supabase.table('slots').update({'status': 'booked'}).eq('slot_id', booking_data.slot_id).execute()

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
        }).execute()
        customer_id = customer_response.data[0]['customer_id']

        # 2. Create the event inquiry
        inquiry_response = supabase.table('event_inquiries').insert({
            'customer_id': customer_id,
            'event_type': inquiry_data.event_type,
            'proposed_date': inquiry_data.proposed_date,
            'guest_count_estimate': inquiry_data.guest_count_estimate,
            'requirements': inquiry_data.requirements
        }).execute()
        inquiry_id = inquiry_response.data[0]['inquiry_id']

        return {"status": "success", "inquiry_id": inquiry_id}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
