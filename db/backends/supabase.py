"""
Supabase database backend implementation.

This backend uses Supabase for cloud-hosted PostgreSQL storage.

SCHEMA NOTE:
The database schema is defined in db/schema.py as the single source of truth.
To generate PostgreSQL/Supabase schema SQL for migrations, run:
    python -m db.schema --generate postgres

Apply the generated SQL in the Supabase dashboard SQL editor or via migrations.
"""

import os
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from db.base import DatabaseBackend
from db.schema import get_postgres_schema, get_table_names
from utils.time import UAE_TZ, get_uae_time

logger = logging.getLogger("proposal-bot")


class SupabaseBackend(DatabaseBackend):
    """
    Supabase database backend implementation.

    Uses Supabase's PostgreSQL database and Storage for cloud persistence.
    """

    def __init__(self):
        """Initialize Supabase backend using environment-aware settings."""
        self._client = None

        # Use the new settings-based config with dev/prod switching
        try:
            from app_settings import settings
            self._url = settings.active_supabase_url or ""
            self._key = settings.active_supabase_service_key or ""

            if self._url and self._key:
                env_name = "PROD" if settings.is_production else "DEV"
                logger.info(f"[SUPABASE] Using {env_name} credentials")
        except ImportError:
            # Fallback to direct env vars (legacy)
            self._url = os.getenv("SUPABASE_URL", "")
            self._key = os.getenv("SUPABASE_SERVICE_KEY", "")

        if not self._url or not self._key:
            logger.warning("[SUPABASE] Credentials not configured. Set SALESBOT_DEV_SUPABASE_URL and SALESBOT_DEV_SUPABASE_SERVICE_ROLE_KEY (or PROD variants)")

    @property
    def name(self) -> str:
        return "supabase"

    def _get_client(self):
        """Get or create Supabase client (lazy initialization)."""
        if self._client is not None:
            return self._client

        if not self._url or not self._key:
            raise RuntimeError("Supabase credentials not configured")

        try:
            from supabase import create_client
            self._client = create_client(self._url, self._key)
            logger.info("[SUPABASE] Client initialized successfully")
            return self._client
        except ImportError:
            raise RuntimeError("supabase package not installed. Run: pip install supabase")
        except Exception as e:
            logger.error(f"[SUPABASE] Failed to initialize client: {e}")
            raise

    def init_db(self) -> None:
        """
        Initialize Supabase schema.

        Note: Unlike SQLite, Supabase schema is typically managed through
        the Supabase dashboard or migrations. This method verifies
        connectivity and logs expected tables from the unified schema.

        To generate the PostgreSQL schema for Supabase, run:
            python -m db.schema --generate postgres
        """
        try:
            client = self._get_client()
            # Log expected tables from unified schema
            expected_tables = get_table_names()
            logger.info(f"[SUPABASE] Expected tables from schema: {expected_tables}")
            logger.info("[SUPABASE] Database connection verified")
            logger.info("[SUPABASE] To regenerate schema SQL: python -m db.schema --generate postgres")
        except Exception as e:
            logger.error(f"[SUPABASE] Failed to initialize: {e}")
            raise

    # =========================================================================
    # PROPOSALS
    # =========================================================================

    def log_proposal(
        self,
        submitted_by: str,
        client_name: str,
        package_type: str,
        locations: str,
        total_amount: str,
        date_generated: Optional[str] = None,
    ) -> None:
        if not date_generated:
            date_generated = datetime.now().isoformat()

        client = self._get_client()
        client.table("proposals_log").insert({
            "submitted_by": submitted_by,
            "client_name": client_name,
            "date_generated": date_generated,
            "package_type": package_type,
            "locations": locations,
            "total_amount": total_amount
        }).execute()

    def get_proposals_summary(self) -> Dict[str, Any]:
        client = self._get_client()

        # Get total count
        response = client.table("proposals_log").select("*", count="exact").execute()
        total_count = response.count or 0

        # Get all for aggregation
        all_proposals = response.data or []

        # Count by package type
        by_type = {}
        for p in all_proposals:
            pt = p.get("package_type", "unknown")
            by_type[pt] = by_type.get(pt, 0) + 1

        # Get recent
        recent_response = client.table("proposals_log").select("client_name,locations,date_generated").order("date_generated", desc=True).limit(5).execute()
        recent = [
            {"client": r["client_name"], "locations": r["locations"], "date": r["date_generated"]}
            for r in (recent_response.data or [])
        ]

        return {
            "total_proposals": total_count,
            "by_package_type": by_type,
            "recent_proposals": recent
        }

    def export_to_excel(self) -> str:
        import pandas as pd
        import tempfile

        client = self._get_client()
        response = client.table("proposals_log").select("*").order("date_generated", desc=True).execute()

        df = pd.DataFrame(response.data or [])
        if not df.empty:
            df['date_generated'] = pd.to_datetime(df['date_generated'])

        temp_file = tempfile.NamedTemporaryFile(
            delete=False,
            suffix=f'_proposals_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        )
        temp_file.close()

        with pd.ExcelWriter(temp_file.name, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Proposals', index=False)

        return temp_file.name

    # =========================================================================
    # BOOKING ORDERS
    # =========================================================================

    def generate_next_bo_ref(self) -> str:
        current_year = datetime.now().year
        client = self._get_client()

        response = client.table("booking_orders").select("bo_ref").like("bo_ref", f"BO-{current_year}-%").order("bo_ref", desc=True).limit(1).execute()

        if response.data:
            last_ref = response.data[0]["bo_ref"]
            last_num = int(last_ref.split("-")[-1])
            next_num = last_num + 1
        else:
            next_num = 1

        return f"BO-{current_year}-{next_num:04d}"

    def save_booking_order(self, data: Dict[str, Any]) -> str:
        client = self._get_client()

        search_text = " ".join([
            str(data.get("bo_ref", "")),
            str(data.get("client", "")),
            str(data.get("brand_campaign", "")),
            str(data.get("bo_number", "")),
        ]).lower()

        record = {
            "bo_ref": data["bo_ref"],
            "company": data["company"],
            "original_file_path": data["original_file_path"],
            "original_file_type": data["original_file_type"],
            "original_file_size": data.get("original_file_size"),
            "original_filename": data.get("original_filename"),
            "parsed_excel_path": data["parsed_excel_path"],
            "bo_number": data.get("bo_number"),
            "bo_date": data.get("bo_date"),
            "client": data.get("client"),
            "agency": data.get("agency"),
            "brand_campaign": data.get("brand_campaign"),
            "category": data.get("category"),
            "asset": json.dumps(data.get("asset")) if isinstance(data.get("asset"), list) else data.get("asset"),
            "net_pre_vat": data.get("net_pre_vat"),
            "vat_value": data.get("vat_value"),
            "gross_amount": data.get("gross_amount"),
            "sla_pct": data.get("sla_pct"),
            "payment_terms": data.get("payment_terms"),
            "sales_person": data.get("sales_person"),
            "commission_pct": data.get("commission_pct"),
            "notes": data.get("notes"),
            "locations_json": json.dumps(data.get("locations", [])),
            "extraction_method": data.get("extraction_method", "llm"),
            "extraction_confidence": data.get("extraction_confidence", "medium"),
            "warnings_json": json.dumps(data.get("warnings", [])),
            "missing_fields_json": json.dumps(data.get("missing_required", [])),
            "vat_calc": data.get("vat_calc"),
            "gross_calc": data.get("gross_calc"),
            "sla_deduction": data.get("sla_deduction"),
            "net_excl_sla_calc": data.get("net_excl_sla_calc"),
            "parsed_at": data.get("parsed_at", datetime.now().isoformat()),
            "parsed_by": data.get("parsed_by"),
            "source_classification": data.get("source_classification"),
            "classification_confidence": data.get("classification_confidence"),
            "needs_review": data.get("needs_review", False),
            "search_text": search_text
        }

        client.table("booking_orders").upsert(record, on_conflict="bo_ref").execute()
        logger.info(f"[SUPABASE] Saved booking order: {data['bo_ref']}")
        return data["bo_ref"]

    def get_booking_order(self, bo_ref: str) -> Optional[Dict[str, Any]]:
        client = self._get_client()
        response = client.table("booking_orders").select("*").eq("bo_ref", bo_ref).single().execute()

        if not response.data:
            return None

        record = response.data
        if record.get("locations_json"):
            record["locations"] = json.loads(record["locations_json"])
        if record.get("warnings_json"):
            record["warnings"] = json.loads(record["warnings_json"])
        if record.get("missing_fields_json"):
            record["missing_required"] = json.loads(record["missing_fields_json"])

        return record

    def get_booking_order_by_number(self, bo_number: str) -> Optional[Dict[str, Any]]:
        client = self._get_client()
        response = client.table("booking_orders").select("*").ilike("bo_number", bo_number.strip()).single().execute()

        if not response.data:
            return None

        record = response.data
        if record.get("locations_json"):
            record["locations"] = json.loads(record["locations_json"])
        if record.get("warnings_json"):
            record["warnings"] = json.loads(record["warnings_json"])
        if record.get("missing_fields_json"):
            record["missing_required"] = json.loads(record["missing_fields_json"])

        return record

    def export_booking_orders_to_excel(self) -> str:
        import pandas as pd
        import tempfile

        client = self._get_client()
        response = client.table("booking_orders").select(
            "bo_ref,bo_number,company,client,brand_campaign,category,gross_amount,net_pre_vat,vat_value,sales_person,parsed_at,notes"
        ).order("parsed_at", desc=True).execute()

        df = pd.DataFrame(response.data or [])
        if not df.empty:
            df['parsed_at'] = pd.to_datetime(df['parsed_at'])
            df.columns = ['BO Reference', 'BO Number', 'Company', 'Client', 'Campaign', 'Category',
                          'Gross Total (AED)', 'Net (AED)', 'VAT (AED)', 'Sales Person',
                          'Created Date', 'Notes']

        temp_file = tempfile.NamedTemporaryFile(
            delete=False,
            suffix=f'_booking_orders_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        )
        temp_file.close()

        with pd.ExcelWriter(temp_file.name, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Booking Orders', index=False)

        return temp_file.name

    # =========================================================================
    # MOCKUP FRAMES
    # =========================================================================

    def save_mockup_frame(
        self,
        location_key: str,
        photo_filename: str,
        frames_data: List[Dict],
        created_by: Optional[str] = None,
        time_of_day: str = "day",
        finish: str = "gold",
        config: Optional[Dict] = None,
    ) -> str:
        import os
        client = self._get_client()

        _, ext = os.path.splitext(photo_filename)
        location_display_name = location_key.replace('_', ' ').title().replace(' ', '')

        # Get existing photos for numbering
        response = client.table("mockup_frames").select("photo_filename").eq("location_key", location_key).execute()
        existing_files = [r["photo_filename"] for r in (response.data or [])]

        existing_numbers = []
        for filename in existing_files:
            name_part = os.path.splitext(filename)[0]
            if name_part.startswith(f"{location_display_name}_"):
                try:
                    num = int(name_part.split('_')[-1])
                    existing_numbers.append(num)
                except ValueError:
                    pass

        next_num = 1
        while next_num in existing_numbers:
            next_num += 1

        final_filename = f"{location_display_name}_{next_num}{ext}"

        client.table("mockup_frames").insert({
            "location_key": location_key,
            "time_of_day": time_of_day,
            "finish": finish,
            "photo_filename": final_filename,
            "frames_data": json.dumps(frames_data),
            "created_at": datetime.now().isoformat(),
            "created_by": created_by,
            "config_json": json.dumps(config) if config else None
        }).execute()

        return final_filename

    def get_mockup_frames(
        self,
        location_key: str,
        photo_filename: str,
        time_of_day: str = "day",
        finish: str = "gold",
    ) -> Optional[List[Dict]]:
        client = self._get_client()
        response = client.table("mockup_frames").select("frames_data").eq("location_key", location_key).eq("time_of_day", time_of_day).eq("finish", finish).eq("photo_filename", photo_filename).single().execute()

        if response.data:
            return json.loads(response.data["frames_data"])
        return None

    def get_mockup_config(
        self,
        location_key: str,
        photo_filename: str,
        time_of_day: str = "day",
        finish: str = "gold",
    ) -> Optional[Dict]:
        client = self._get_client()
        response = client.table("mockup_frames").select("config_json").eq("location_key", location_key).eq("time_of_day", time_of_day).eq("finish", finish).eq("photo_filename", photo_filename).single().execute()

        if response.data and response.data.get("config_json"):
            return json.loads(response.data["config_json"])
        return None

    def list_mockup_photos(
        self,
        location_key: str,
        time_of_day: str = "day",
        finish: str = "gold",
    ) -> List[str]:
        client = self._get_client()
        response = client.table("mockup_frames").select("photo_filename").eq("location_key", location_key).eq("time_of_day", time_of_day).eq("finish", finish).execute()

        return [r["photo_filename"] for r in (response.data or [])]

    def list_mockup_variations(self, location_key: str) -> Dict[str, List[str]]:
        client = self._get_client()
        response = client.table("mockup_frames").select("time_of_day,finish").eq("location_key", location_key).execute()

        variations = {}
        for r in (response.data or []):
            tod = r["time_of_day"]
            fin = r["finish"]
            if tod not in variations:
                variations[tod] = []
            if fin not in variations[tod]:
                variations[tod].append(fin)

        return variations

    def delete_mockup_frame(
        self,
        location_key: str,
        photo_filename: str,
        time_of_day: str = "day",
        finish: str = "gold",
    ) -> None:
        client = self._get_client()
        client.table("mockup_frames").delete().eq("location_key", location_key).eq("time_of_day", time_of_day).eq("finish", finish).eq("photo_filename", photo_filename).execute()

    # =========================================================================
    # MOCKUP USAGE
    # =========================================================================

    def log_mockup_usage(
        self,
        location_key: str,
        time_of_day: str,
        finish: str,
        photo_used: str,
        creative_type: str,
        ai_prompt: Optional[str] = None,
        template_selected: bool = False,
        success: bool = True,
        user_ip: Optional[str] = None,
    ) -> None:
        client = self._get_client()
        client.table("mockup_usage").insert({
            "generated_at": datetime.now().isoformat(),
            "location_key": location_key,
            "time_of_day": time_of_day,
            "finish": finish,
            "photo_used": photo_used,
            "creative_type": creative_type,
            "ai_prompt": ai_prompt,
            "template_selected": template_selected,
            "success": success,
            "user_ip": user_ip
        }).execute()

    def get_mockup_usage_stats(self) -> Dict[str, Any]:
        client = self._get_client()

        response = client.table("mockup_usage").select("*").execute()
        all_usage = response.data or []

        total_count = len(all_usage)
        successful = sum(1 for u in all_usage if u.get("success"))
        failed = total_count - successful

        by_location = {}
        by_creative_type = {}
        with_template = 0
        without_template = 0

        for u in all_usage:
            loc = u.get("location_key", "unknown")
            by_location[loc] = by_location.get(loc, 0) + 1

            ct = u.get("creative_type", "unknown")
            by_creative_type[ct] = by_creative_type.get(ct, 0) + 1

            if u.get("template_selected"):
                with_template += 1
            else:
                without_template += 1

        # Get recent
        recent_response = client.table("mockup_usage").select("location_key,creative_type,generated_at,success").order("generated_at", desc=True).limit(10).execute()
        recent = [
            {
                "location": r["location_key"],
                "creative_type": r["creative_type"],
                "generated_at": r["generated_at"],
                "success": r["success"]
            }
            for r in (recent_response.data or [])
        ]

        return {
            "total_generations": total_count,
            "successful": successful,
            "failed": failed,
            "by_location": by_location,
            "by_creative_type": by_creative_type,
            "with_template": with_template,
            "without_template": without_template,
            "recent_generations": recent
        }

    def export_mockup_usage_to_excel(self) -> str:
        import pandas as pd
        import tempfile

        client = self._get_client()
        response = client.table("mockup_usage").select("*").order("generated_at", desc=True).execute()

        df = pd.DataFrame(response.data or [])
        if not df.empty:
            df['generated_at'] = pd.to_datetime(df['generated_at'])
            df['template_selected'] = df['template_selected'].map({True: 'Yes', False: 'No'})
            df['success'] = df['success'].map({True: 'Success', False: 'Failed'})

        temp_file = tempfile.NamedTemporaryFile(
            delete=False,
            suffix=f'_mockup_usage_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        )
        temp_file.close()

        with pd.ExcelWriter(temp_file.name, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Mockup Usage', index=False)

        return temp_file.name

    # =========================================================================
    # BO WORKFLOWS
    # =========================================================================

    def save_bo_workflow(
        self,
        workflow_id: str,
        workflow_data: str,
        updated_at: str,
    ) -> None:
        client = self._get_client()
        client.table("bo_approval_workflows").upsert({
            "workflow_id": workflow_id,
            "workflow_data": workflow_data,
            "updated_at": updated_at
        }, on_conflict="workflow_id").execute()

    def get_bo_workflow(self, workflow_id: str) -> Optional[str]:
        client = self._get_client()
        response = client.table("bo_approval_workflows").select("workflow_data").eq("workflow_id", workflow_id).single().execute()

        return response.data["workflow_data"] if response.data else None

    def get_all_active_bo_workflows(self) -> List[tuple]:
        client = self._get_client()
        response = client.table("bo_approval_workflows").select("workflow_id,workflow_data").order("updated_at", desc=True).execute()

        return [(r["workflow_id"], r["workflow_data"]) for r in (response.data or [])]

    def delete_bo_workflow(self, workflow_id: str) -> None:
        client = self._get_client()
        client.table("bo_approval_workflows").delete().eq("workflow_id", workflow_id).execute()

    # =========================================================================
    # AI COSTS
    # =========================================================================

    def log_ai_cost(
        self,
        call_type: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        reasoning_tokens: int,
        input_cost: float,
        output_cost: float,
        reasoning_cost: float,
        total_cost: float,
        user_id: Optional[str] = None,
        workflow: Optional[str] = None,
        cached_input_tokens: int = 0,
        context: Optional[str] = None,
        metadata_json: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> None:
        if not timestamp:
            timestamp = get_uae_time().isoformat()

        total_tokens = input_tokens + output_tokens + reasoning_tokens

        client = self._get_client()
        client.table("ai_costs").insert({
            "timestamp": timestamp,
            "call_type": call_type,
            "workflow": workflow,
            "model": model,
            "user_id": user_id,
            "context": context,
            "input_tokens": input_tokens,
            "cached_input_tokens": cached_input_tokens,
            "output_tokens": output_tokens,
            "reasoning_tokens": reasoning_tokens,
            "total_tokens": total_tokens,
            "input_cost": input_cost,
            "output_cost": output_cost,
            "reasoning_cost": reasoning_cost,
            "total_cost": total_cost,
            "metadata_json": metadata_json
        }).execute()

        logger.info(f"[SUPABASE COSTS] Logged {call_type}: ${total_cost:.4f}")

    def get_ai_costs_summary(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        call_type: Optional[str] = None,
        workflow: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        client = self._get_client()

        # Build query with filters
        query = client.table("ai_costs").select("*")

        if start_date:
            query = query.gte("timestamp", start_date)
        if end_date:
            end_date_full = f"{end_date}T23:59:59" if 'T' not in end_date else end_date
            query = query.lte("timestamp", end_date_full)
        if call_type:
            query = query.eq("call_type", call_type)
        if workflow:
            query = query.eq("workflow", workflow)
        if user_id:
            query = query.eq("user_id", user_id)

        response = query.execute()
        all_costs = response.data or []

        # Calculate aggregations
        total_calls = len(all_costs)
        total_tokens = sum(c.get("total_tokens", 0) for c in all_costs)
        total_cost = sum(c.get("total_cost", 0) for c in all_costs)
        total_input = sum(c.get("input_tokens", 0) for c in all_costs)
        total_output = sum(c.get("output_tokens", 0) for c in all_costs)
        total_reasoning = sum(c.get("reasoning_tokens", 0) for c in all_costs)
        total_cached = sum(c.get("cached_input_tokens", 0) for c in all_costs)

        # Group by call_type
        by_call_type = {}
        for c in all_costs:
            ct = c.get("call_type", "unknown")
            if ct not in by_call_type:
                by_call_type[ct] = {"calls": 0, "tokens": 0, "cost": 0}
            by_call_type[ct]["calls"] += 1
            by_call_type[ct]["tokens"] += c.get("total_tokens", 0)
            by_call_type[ct]["cost"] += c.get("total_cost", 0)

        # Group by workflow
        by_workflow = {}
        for c in all_costs:
            wf = c.get("workflow") or "none"
            if wf not in by_workflow:
                by_workflow[wf] = {"calls": 0, "tokens": 0, "cost": 0}
            by_workflow[wf]["calls"] += 1
            by_workflow[wf]["tokens"] += c.get("total_tokens", 0)
            by_workflow[wf]["cost"] += c.get("total_cost", 0)

        # Group by model
        by_model = {}
        for c in all_costs:
            m = c.get("model", "unknown")
            if m not in by_model:
                by_model[m] = {"calls": 0, "tokens": 0, "cost": 0}
            by_model[m]["calls"] += 1
            by_model[m]["tokens"] += c.get("total_tokens", 0)
            by_model[m]["cost"] += c.get("total_cost", 0)

        # Group by user
        by_user = {}
        for c in all_costs:
            u = c.get("user_id")
            if u:
                if u not in by_user:
                    by_user[u] = {"calls": 0, "tokens": 0, "cost": 0}
                by_user[u]["calls"] += 1
                by_user[u]["tokens"] += c.get("total_tokens", 0)
                by_user[u]["cost"] += c.get("total_cost", 0)

        # Daily costs
        daily = {}
        for c in all_costs:
            date = c.get("timestamp", "")[:10]
            if date not in daily:
                daily[date] = {"calls": 0, "cost": 0}
            daily[date]["calls"] += 1
            daily[date]["cost"] += c.get("total_cost", 0)

        daily_costs = [{"date": d, "calls": v["calls"], "cost": v["cost"]} for d, v in sorted(daily.items())]

        # Recent calls
        recent_response = client.table("ai_costs").select(
            "id,timestamp,call_type,workflow,model,input_tokens,output_tokens,reasoning_tokens,cached_input_tokens,total_cost,user_id"
        ).order("timestamp", desc=True).limit(100).execute()

        calls = [
            {
                "id": r["id"], "timestamp": r["timestamp"], "call_type": r["call_type"],
                "workflow": r["workflow"], "model": r["model"], "input_tokens": r["input_tokens"],
                "output_tokens": r["output_tokens"], "reasoning_tokens": r["reasoning_tokens"],
                "cached_input_tokens": r["cached_input_tokens"], "total_cost": r["total_cost"],
                "user_id": r["user_id"]
            }
            for r in (recent_response.data or [])
        ]

        return {
            "total_calls": total_calls,
            "total_tokens": total_tokens,
            "total_cost": total_cost,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_reasoning_tokens": total_reasoning,
            "total_cached_tokens": total_cached,
            "by_call_type": by_call_type,
            "by_workflow": by_workflow,
            "by_model": by_model,
            "by_user": by_user,
            "daily_costs": daily_costs,
            "calls": calls
        }

    def clear_ai_costs(self) -> None:
        client = self._get_client()
        # Delete all records - Supabase doesn't have a truncate
        client.table("ai_costs").delete().neq("id", 0).execute()
        logger.info("[SUPABASE] Cleared all AI cost tracking data")

    # =========================================================================
    # USER MANAGEMENT
    # =========================================================================

    def upsert_user(
        self,
        user_id: str,
        email: str,
        full_name: Optional[str] = None,
        avatar_url: Optional[str] = None,
        created_at: Optional[str] = None,
        last_login: Optional[str] = None,
    ) -> bool:
        if not created_at:
            created_at = datetime.now().isoformat()
        if not last_login:
            last_login = datetime.now().isoformat()

        now = datetime.now().isoformat()

        try:
            client = self._get_client()
            client.table("users").upsert({
                "id": user_id,
                "email": email,
                "name": full_name,
                "avatar_url": avatar_url,
                "created_at": created_at,
                "updated_at": now,
                "last_login_at": last_login,
                "is_active": True,
            }, on_conflict="id").execute()

            logger.info(f"[SUPABASE] Upserted user: {email}")
            return True
        except Exception as e:
            logger.error(f"[SUPABASE] Error upserting user: {e}")
            return False

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        try:
            client = self._get_client()
            response = client.table("users").select("*").eq("id", user_id).single().execute()
            return response.data
        except Exception:
            return None

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        try:
            client = self._get_client()
            response = client.table("users").select("*").ilike("email", email).single().execute()
            return response.data
        except Exception:
            return None

    # =========================================================================
    # RBAC: ROLES
    # =========================================================================

    def get_role_by_name(self, role_name: str) -> Optional[Dict[str, Any]]:
        try:
            client = self._get_client()
            response = client.table("roles").select("*").eq("name", role_name).single().execute()
            return response.data
        except Exception:
            return None

    def list_roles(self) -> List[Dict[str, Any]]:
        try:
            client = self._get_client()
            response = client.table("roles").select("*").order("name").execute()
            return response.data or []
        except Exception as e:
            logger.error(f"[SUPABASE] Error listing roles: {e}")
            return []

    def create_role(
        self,
        name: str,
        description: Optional[str] = None,
        is_system: bool = False,
        created_at: Optional[str] = None,
    ) -> Optional[str]:
        if not created_at:
            created_at = datetime.now().isoformat()

        try:
            client = self._get_client()
            response = client.table("roles").upsert({
                "name": name,
                "description": description,
                "is_system": is_system,
                "created_at": created_at,
            }, on_conflict="name").execute()

            if response.data:
                role_id = str(response.data[0]["id"])
                logger.info(f"[SUPABASE] Created/updated role: {name} (id={role_id})")
                return role_id
            return None
        except Exception as e:
            logger.error(f"[SUPABASE] Error creating role: {e}")
            return None

    def update_role(
        self,
        role_id: str,
        description: Optional[str] = None,
    ) -> bool:
        try:
            client = self._get_client()
            client.table("roles").update({"description": description}).eq("id", role_id).execute()
            return True
        except Exception as e:
            logger.error(f"[SUPABASE] Error updating role: {e}")
            return False

    def delete_role(self, role_id: str) -> bool:
        try:
            client = self._get_client()
            # Delete role_permissions first
            client.table("role_permissions").delete().eq("role_id", role_id).execute()
            # Delete user_roles
            client.table("user_roles").delete().eq("role_id", role_id).execute()
            # Delete the role
            client.table("roles").delete().eq("id", role_id).execute()
            logger.info(f"[SUPABASE] Deleted role: {role_id}")
            return True
        except Exception as e:
            logger.error(f"[SUPABASE] Error deleting role: {e}")
            return False

    # =========================================================================
    # RBAC: PERMISSIONS
    # =========================================================================

    def list_permissions(self) -> List[Dict[str, Any]]:
        try:
            client = self._get_client()
            response = client.table("permissions").select("*").order("name").execute()
            return response.data or []
        except Exception as e:
            logger.error(f"[SUPABASE] Error listing permissions: {e}")
            return []

    def create_permission(
        self,
        name: str,
        resource: str,
        action: str,
        description: Optional[str] = None,
        created_at: Optional[str] = None,
    ) -> Optional[str]:
        if not created_at:
            created_at = datetime.now().isoformat()

        try:
            client = self._get_client()
            response = client.table("permissions").upsert({
                "name": name,
                "resource": resource,
                "action": action,
                "description": description,
                "created_at": created_at,
            }, on_conflict="name").execute()

            if response.data:
                perm_id = str(response.data[0]["id"])
                logger.debug(f"[SUPABASE] Created/updated permission: {name}")
                return perm_id
            return None
        except Exception as e:
            logger.error(f"[SUPABASE] Error creating permission: {e}")
            return None

    def get_role_permissions(self, role_id: str) -> List[Dict[str, Any]]:
        try:
            client = self._get_client()
            # Join role_permissions with permissions
            response = client.table("role_permissions").select(
                "permission_id, permissions(*)"
            ).eq("role_id", role_id).execute()

            permissions = []
            for rp in (response.data or []):
                if rp.get("permissions"):
                    permissions.append(rp["permissions"])

            return permissions
        except Exception as e:
            logger.error(f"[SUPABASE] Error getting role permissions: {e}")
            return []

    def assign_role_permission(
        self,
        role_id: str,
        permission_name: str,
        assigned_at: Optional[str] = None,
    ) -> bool:
        if not assigned_at:
            assigned_at = datetime.now().isoformat()

        try:
            client = self._get_client()
            # Get permission ID
            perm_response = client.table("permissions").select("id").eq("name", permission_name).single().execute()
            if not perm_response.data:
                logger.warning(f"[SUPABASE] Permission not found: {permission_name}")
                return False
            perm_id = perm_response.data["id"]

            client.table("role_permissions").upsert({
                "role_id": role_id,
                "permission_id": perm_id,
                "granted_at": assigned_at,
            }, on_conflict="role_id,permission_id").execute()
            return True
        except Exception as e:
            logger.error(f"[SUPABASE] Error assigning role permission: {e}")
            return False

    def set_role_permissions(
        self,
        role_id: str,
        permission_names: List[str],
        assigned_at: Optional[str] = None,
    ) -> bool:
        if not assigned_at:
            assigned_at = datetime.now().isoformat()

        try:
            client = self._get_client()
            # Remove existing permissions
            client.table("role_permissions").delete().eq("role_id", role_id).execute()

            # Add new permissions
            for perm_name in permission_names:
                perm_response = client.table("permissions").select("id").eq("name", perm_name).single().execute()
                if perm_response.data:
                    client.table("role_permissions").insert({
                        "role_id": role_id,
                        "permission_id": perm_response.data["id"],
                        "granted_at": assigned_at,
                    }).execute()

            return True
        except Exception as e:
            logger.error(f"[SUPABASE] Error setting role permissions: {e}")
            return False

    # =========================================================================
    # RBAC: USER ROLES
    # =========================================================================

    def get_user_roles(self, user_id: str) -> List[Dict[str, Any]]:
        try:
            client = self._get_client()
            # Join user_roles with roles
            response = client.table("user_roles").select(
                "role_id, granted_at, granted_by, expires_at, roles(*)"
            ).eq("user_id", user_id).execute()

            roles = []
            now = datetime.now(UAE_TZ).isoformat()
            for ur in (response.data or []):
                # Check if expired
                if ur.get("expires_at") and ur["expires_at"] < now:
                    continue
                if ur.get("roles"):
                    role = ur["roles"]
                    role["granted_at"] = ur.get("granted_at")
                    role["granted_by"] = ur.get("granted_by")
                    role["expires_at"] = ur.get("expires_at")
                    roles.append(role)

            return roles
        except Exception as e:
            logger.error(f"[SUPABASE] Error getting user roles: {e}")
            return []

    def assign_user_role(
        self,
        user_id: str,
        role_id: str,
        granted_by: Optional[str] = None,
        granted_at: Optional[str] = None,
        expires_at: Optional[str] = None,
    ) -> bool:
        if not granted_at:
            granted_at = datetime.now().isoformat()

        try:
            client = self._get_client()
            client.table("user_roles").upsert({
                "user_id": user_id,
                "role_id": role_id,
                "granted_by": granted_by,
                "granted_at": granted_at,
                "expires_at": expires_at,
            }, on_conflict="user_id,role_id").execute()

            logger.info(f"[SUPABASE] Assigned role {role_id} to user {user_id}")
            return True
        except Exception as e:
            logger.error(f"[SUPABASE] Error assigning user role: {e}")
            return False

    def revoke_user_role(self, user_id: str, role_name: str) -> bool:
        try:
            client = self._get_client()
            # Get role ID
            role_response = client.table("roles").select("id").eq("name", role_name).single().execute()
            if not role_response.data:
                logger.warning(f"[SUPABASE] Role not found: {role_name}")
                return False
            role_id = role_response.data["id"]

            client.table("user_roles").delete().eq("user_id", user_id).eq("role_id", role_id).execute()
            logger.info(f"[SUPABASE] Revoked role {role_name} from user {user_id}")
            return True
        except Exception as e:
            logger.error(f"[SUPABASE] Error revoking user role: {e}")
            return False
