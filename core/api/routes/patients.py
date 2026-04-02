from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from core.api.deps import get_db
from core.db.models import Patient

router = APIRouter()


class PatientCreate(BaseModel):
    full_name: str | None = None
    medical_summary: str | None = None


class PatientUpdate(BaseModel):
    full_name: str | None = None
    medical_summary: str | None = None


class PatientOut(BaseModel):
    id: str
    full_name: str | None
    medical_summary: str | None
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("", response_model=list[PatientOut])
def list_patients(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    return db.query(Patient).order_by(Patient.created_at.desc()).offset(skip).limit(limit).all()


@router.get("/{patient_id}", response_model=PatientOut)
def get_patient(patient_id: str, db: Session = Depends(get_db)):
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient


@router.post("", response_model=PatientOut, status_code=201)
def create_patient(body: PatientCreate, db: Session = Depends(get_db)):
    patient = Patient(full_name=body.full_name, medical_summary=body.medical_summary)
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return patient


@router.put("/{patient_id}", response_model=PatientOut)
def update_patient(patient_id: str, body: PatientUpdate, db: Session = Depends(get_db)):
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    if body.full_name is not None:
        patient.full_name = body.full_name
    if body.medical_summary is not None:
        patient.medical_summary = body.medical_summary
    db.commit()
    db.refresh(patient)
    return patient


@router.delete("/{patient_id}", status_code=204)
def delete_patient(patient_id: str, db: Session = Depends(get_db)):
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    db.delete(patient)
    db.commit()
    return None
