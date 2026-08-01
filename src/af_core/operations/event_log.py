import json
from sqlalchemy import select
from af_core.persistence.tables import EventRow

class EventLog:
    def __init__(self,sessions):
        self.sessions=sessions

    def append(self,event_type,project_id,payload):
        with self.sessions() as s:
            row=EventRow(
                event_type=event_type,
                project_id=project_id,
                payload=json.dumps(payload),
            )
            s.add(row)
            s.commit()
            s.refresh(row)
            return row.sequence

    def list_for_project(self,project_id):
        with self.sessions() as s:
            rows=s.scalars(
                select(EventRow)
                .where(EventRow.project_id==project_id)
                .order_by(EventRow.sequence)
            ).all()
            return [
                {
                    "sequence":r.sequence,
                    "event_type":r.event_type,
                    "payload":json.loads(r.payload),
                }
                for r in rows
            ]
