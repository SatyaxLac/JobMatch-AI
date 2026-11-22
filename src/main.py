"""
Job-Match — legacy Streamlit entry point.

This is the **only** file that imports Streamlit. All business logic lives
in the ``services/`` layer; ``display_jobs.py`` receives its UI dependency
from this module without importing Streamlit itself.
"""

import logging
import math
import re
import sys
import time

import streamlit as st
import pydeck as pdk
from sqlalchemy.orm import joinedload

# ---------------------------------------------------------------------------
# Services (no Streamlit dependency)
# ---------------------------------------------------------------------------
from services.search_service import start_job_search
from services.enrichment_service import (
    summarize_and_embed,
    clear_summarizations,
    clear_embeddings,
)
from services.chat_service import (
    send_prompt_to_llm,
    get_resume_summary,
    get_resume_text,
)
from services.resume_service import summarize_resume
from services.personalized_service import build_resume_and_cover_letter

# ---------------------------------------------------------------------------
# Data-access helpers (no Streamlit dependency)
# ---------------------------------------------------------------------------
import config
from models_sql import init_db, Session, Job, Profile
from db_profiles import (
    get_all_profiles,
    load_profile,
    save_profile,
    set_active_profile,
    get_active_profile,
    clear_resume,
)
from models_redis import redis_client
from nominatim_api import get_coordinates
from locale_utils import get_countries, get_languages

# ---------------------------------------------------------------------------
# UI view helpers receive the Streamlit module from this entry point.
# ---------------------------------------------------------------------------
from display_jobs import process_results, show_jobs

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (moved from sidebar_processor)
# ---------------------------------------------------------------------------
EMPLOYMENT_TYPE_OPTIONS = {
    "Full Time":  "FULLTIME",
    "Part Time":  "PARTTIME",
    "Contractor": "CONTRACTOR",
    "Internship": "INTERN",
}

EXPERIENCE_OPTIONS = {
    "Less than 3 years":      "under_3_years_experience",
    "More than 3 years":      "more_than_3_years_experience",
    "No Experience Required": "no_experience",
    "No Degree Required":     "no_degree",
}


# ===================================================================
#  Pure helpers (no widgets — only read/compute/return)
# ===================================================================

def _default_filters() -> dict:
    return {
        "keywords": "software engineer",
        "location": "California",
        "country": "United States",
        "language": "English",
        "date_posted": "all",
        "work_from_home": False,
        "employment_types": [],
        "job_requirements": [],
        "company_input": "",
        "salary_range": [80000, 180000],
        "distance_radius": 50,
        "max_jobs": 100,
    }


def _get_current_filters() -> dict:
    return {
        "keywords":         st.session_state.get("keywords", "software engineer"),
        "location":         st.session_state.get("location", "California"),
        "country":          st.session_state.get("country_name", "United States"),
        "language":         st.session_state.get("language_name", "English"),
        "date_posted":      st.session_state.get("date_posted", "all"),
        "work_from_home":   st.session_state.get("work_from_home", False),
        "employment_types": st.session_state.get("employment_types", []),
        "job_requirements": st.session_state.get("job_requirements", []),
        "company_input":    st.session_state.get("company_input", ""),
        "salary_range": [
            st.session_state.get("salary_range", [80000, 180000])[0],
            st.session_state.get("salary_range", [80000, 180000])[1],
        ],
        "distance_radius":  st.session_state.get("distance_radius", 50),
        "max_jobs":         st.session_state.get("max_jobs", 100),
    }


def _get_visible_jobs():
    return (
        st.session_state.get("visible_job_ids_fav")
        or st.session_state.get("visible_job_ids")
    )


def _is_valid_profile_name(name: str) -> bool:
    return re.match(r"^[a-zA-Z0-9_-]{1,50}$", name) is not None


# ===================================================================
#  Sidebar callbacks
# ===================================================================

def _on_profile_change():
    selected = st.session_state["selected_profile"]
    set_active_profile(selected)
    st.session_state["visible_job_ids"] = None
    st.session_state["visible_job_ids_fav"] = None


def _on_create_profile():
    name = st.session_state.get("profile_name", "").strip()
    if not name:
        return
    if name in get_all_profiles():
        st.warning("Profile already exists.")
        return
    if not _is_valid_profile_name(name):
        st.error("Invalid name. Use only letters, numbers, _ or - (max 50 chars).")
        return
    save_profile(name, filter_data=_get_current_filters())
    set_active_profile(name)
    st.session_state["profile_name"] = ""


def _on_location_change():
    my_location = st.session_state.get("my_location", "").strip()
    active_profile_name = get_active_profile()
    if not my_location or not active_profile_name:
        return
    status, output = get_coordinates(my_location)
    if not status:
        st.error(f"Failed to set location. {output}")
        return
    latitude, longitude = output
    save_profile(
        active_profile_name,
        my_location=my_location,
        latitude=latitude,
        longitude=longitude,
    )
    alert = st.success(f"📍 Location set: {my_location} ({latitude}, {longitude})")
    time.sleep(3)
    alert.empty()


def _on_filter_change():
    active_profile_name = get_active_profile()
    if active_profile_name:
        save_profile(active_profile_name, filter_data=_get_current_filters())


# ===================================================================
#  Initialisation
# ===================================================================

init_db()

if "default" not in get_all_profiles():
    save_profile("default", filter_data=_default_filters())
    set_active_profile("default")

st.set_page_config(page_title="Job-Match", layout="wide")
st.title("🧠 Job-Match: Smarter Job Search")

if "job_id_list" not in st.session_state:
    st.session_state["job_id_list"] = []


# ===================================================================
#  Sidebar rendering
# ===================================================================

with st.sidebar:

    # ── Profile ────────────────────────────────────────────────────
    st.header("👤 Profile")

    all_profiles = get_all_profiles()
    if not all_profiles:
        st.error("No user profile found!")
        sys.exit(1)

    active_profile_name = get_active_profile()
    active_profile_index = all_profiles.index(active_profile_name)

    st.selectbox(
        "Select Profile",
        options=all_profiles,
        index=active_profile_index,
        key="selected_profile",
        on_change=_on_profile_change,
    )

    st.text_input(
        "Create New Profile",
        placeholder="Enter name and press Enter",
        key="profile_name",
        on_change=_on_create_profile,
    )

    profile_data = load_profile(active_profile_name)

    # ── Favorites ──────────────────────────────────────────────────
    st.header("⭐ Favorites")

    if "show_favorites_pane" not in st.session_state:
        st.session_state.show_favorites_pane = False

    if st.button("📝 View Favorite Jobs"):
        st.session_state.show_favorites_pane = True

    # ── Location ───────────────────────────────────────────────────
    st.header("📍 Location")

    my_location = profile_data.get("my_location")
    st.text_input(
        "Your Location",
        placeholder=my_location or "Enter city name and press Enter",
        key="my_location",
        on_change=_on_location_change,
    )

    # ── Filters ────────────────────────────────────────────────────
    st.header("🎯 Filters")

    st.text_input(
        "Keywords",
        profile_data.get("keywords", "software engineer"),
        key="keywords",
        on_change=_on_filter_change,
    )
    st.text_input(
        "Location",
        profile_data.get("location", "California"),
        key="location",
        on_change=_on_filter_change,
    )

    countries_dict = get_countries()
    default_country = profile_data.get("country", "United States")
    st.selectbox(
        "Country",
        list(countries_dict.keys()),
        index=list(countries_dict.keys()).index(default_country),
        key="country_name",
        on_change=_on_filter_change,
    )

    languages_dict = get_languages()
    default_language = profile_data.get("language", "English")
    st.selectbox(
        "Language",
        list(languages_dict.keys()),
        index=list(languages_dict.keys()).index(default_language),
        key="language_name",
        on_change=_on_filter_change,
    )

    st.selectbox(
        "Date Posted",
        ["all", "today", "3days", "week", "month"],
        index=["all", "today", "3days", "week", "month"].index(
            profile_data.get("date_posted", "all")
        ),
        key="date_posted",
        on_change=_on_filter_change,
    )

    st.checkbox(
        "Remote Only",
        value=profile_data.get("work_from_home", False),
        key="work_from_home",
        on_change=_on_filter_change,
    )

    st.multiselect(
        "Employment Types",
        list(EMPLOYMENT_TYPE_OPTIONS.keys()),
        default=profile_data.get("employment_types", []),
        key="employment_types",
        on_change=_on_filter_change,
    )

    st.multiselect(
        "Experience",
        list(EXPERIENCE_OPTIONS.keys()),
        default=profile_data.get("job_requirements", []),
        key="job_requirements",
        on_change=_on_filter_change,
    )

    st.text_input(
        "Company Names (comma-separated)",
        profile_data.get("company_input", ""),
        key="company_input",
        on_change=_on_filter_change,
    )

    st.slider(
        "Expected Salary Range (Annual USD)",
        min_value=10000,
        max_value=500000,
        value=tuple(profile_data.get("salary_range", (80000, 180000))),
        step=5000,
        key="salary_range",
        on_change=_on_filter_change,
    )

    location_set = bool(profile_data.get("my_location"))

    st.slider(
        "Maximum Distance from Location (miles)",
        min_value=5,
        max_value=100,
        value=profile_data.get("distance_radius", 30),
        step=5,
        key="distance_radius",
        on_change=_on_filter_change,
        disabled=not location_set,
    )

    # ── Location map ───────────────────────────────────────────────
    my_latitude = profile_data.get("latitude")
    my_longitude = profile_data.get("longitude")
    radius_miles = st.session_state.get("distance_radius")

    if my_latitude is not None and my_longitude is not None and radius_miles:

        if "show_map" not in st.session_state:
            st.session_state["show_map"] = False

        if st.button("🗺️ Show My Location on Map"):
            st.session_state["show_map"] = True

        if st.session_state["show_map"]:
            with st.expander("📍 My Location Map", expanded=True):
                radius_meters = radius_miles * 1609.34
                zoom = 14 - math.log2(radius_meters / 500) + 0.7
                zoom = max(min(zoom, 20), 1)

                area_layer = pdk.Layer(
                    "ScatterplotLayer",
                    data=[{"position": [my_longitude, my_latitude]}],
                    get_position="position",
                    get_radius=radius_meters,
                    get_fill_color=[255, 0, 0, 60],
                    get_line_color=[255, 0, 0],
                    pickable=False,
                )
                center_layer = pdk.Layer(
                    "ScatterplotLayer",
                    data=[{"position": [my_longitude, my_latitude]}],
                    get_position="position",
                    get_radius=500,
                    get_fill_color=[0, 255, 0, 200],
                    get_line_color=[0, 128, 0],
                    pickable=False,
                )
                view_state = pdk.ViewState(
                    latitude=my_latitude, longitude=my_longitude, zoom=zoom,
                )
                st.pydeck_chart(
                    pdk.Deck(
                        map_style=config.map_style_jobs,
                        initial_view_state=view_state,
                        layers=[area_layer, center_layer],
                    )
                )

    # ── Max jobs ───────────────────────────────────────────────────
    st.slider(
        "Max Jobs",
        10, 300,
        profile_data.get("max_jobs", 100),
        key="max_jobs",
        on_change=_on_filter_change,
    )

    # ── Resume upload ──────────────────────────────────────────────
    st.header("📄 Resume Upload")

    profile = load_profile(active_profile_name)

    if profile and profile["resume_filename"]:
        st.success(f"📎 Resume attached: {profile['resume_filename']}")

        if st.button("❌ Remove Resume", key="remove_resume"):
            clear_resume(active_profile_name)
            st.rerun()
    else:
        uploaded_file = st.file_uploader("Upload your resume", key="resume_upload")

        if uploaded_file:
            resume_filename = uploaded_file.name
            resume_bytes = uploaded_file.read()
            save_profile(
                active_profile_name,
                resume_filename=resume_filename,
                resume_binary=resume_bytes,
            )
            with st.status("Preparing Resume…", expanded=True) as resume_status:
                status, error = summarize_resume(
                    active_profile_name,
                    on_progress=lambda msg: st.write(msg),
                )
                if status:
                    resume_status.update(
                        label="Resume preparation complete",
                        state="complete",
                        expanded=False,
                    )
                else:
                    st.error(error)
            st.rerun()

    # ── Enrich + LLM ──────────────────────────────────────────────
    st.divider()

    if st.button("Enrich Jobs", key="enrich_jobs"):
        visible_job_ids = _get_visible_jobs()
        if not visible_job_ids:
            st.warning("No job listings are currently visible to reference.")
        else:
            with st.status("Enriching jobs…", expanded=True) as enrich_status:
                status, output = summarize_and_embed(
                    visible_job_ids,
                    on_progress=lambda msg: st.write(msg),
                )
                if status:
                    enrich_status.update(
                        label="Enrichment complete!",
                        state="complete",
                        expanded=False,
                    )
                else:
                    st.warning(output)

    st.header(f"🤖 Ask the Assistant ({config.llm_model_chat})")

    user_prompt = st.text_area(
        "Enter your question or prompt below:",
        height=150,
        key="llm_user_prompt",
    )

    if st.button("💬 Ask LLM", key="ask_llm_btn"):
        user_prompt = user_prompt.strip()
        if not user_prompt:
            st.warning("Please enter a prompt before submitting.")
        else:
            visible_job_ids = _get_visible_jobs()
            if not visible_job_ids:
                st.warning("No job listings are currently visible to reference.")
            else:
                # Ensure enrichment is done first
                with st.status("Preparing context…", expanded=True) as prep_status:
                    status, output = summarize_and_embed(
                        visible_job_ids,
                        on_progress=lambda msg: st.write(msg),
                    )
                    if status:
                        prep_status.update(
                            label="Context ready",
                            state="complete",
                            expanded=False,
                        )
                    else:
                        st.warning(output)
                        st.stop()

                # Run RAG chat
                with st.status("Generating advice…", expanded=True) as llm_status:
                    profile_name = st.session_state.get("selected_profile", "default")
                    resume_sum = get_resume_summary(profile_name)

                    status, output = send_prompt_to_llm(
                        user_prompt,
                        visible_job_ids,
                        resume_summary=resume_sum,
                        on_progress=lambda msg: st.write(msg),
                    )
                    if status:
                        st.session_state["llm_response"] = output
                        llm_status.update(
                            label="Response received!",
                            state="complete",
                            expanded=False,
                        )
                    else:
                        st.warning(output)

    # ── Housekeeping ───────────────────────────────────────────────
    st.divider()

    if st.button("🗑️ Clear Job Cache", use_container_width=False):
        try:
            redis_client.flushdb()
            st.success("✅ Redis job cache cleared.")
        except Exception as e:
            st.error(f"❌ Failed to clear Redis cache: {e}")

    if st.button("🗑️ Clear All Summarizations", use_container_width=False):
        try:
            clear_summarizations()
            st.success("✅ Cleared summarization.")
        except Exception as e:
            st.error(f"❌ Failed to clear summarizations: {e}")

    if st.button("🗑️ Clear All Embeddings", use_container_width=False):
        try:
            clear_embeddings()
            st.success("✅ Cleared embeddings.")
        except Exception as e:
            st.error(f"❌ Failed to clear embeddings: {e}")


# ===================================================================
#  Main content area
# ===================================================================

# ── Resume / Cover-letter generation ──────────────────────────────

if st.session_state.get("generate_resume"):

    job = st.session_state["generate_resume"]

    if "resume_output" not in st.session_state:
        profile_name = st.session_state.get("selected_profile", "default")
        resume_text = get_resume_text(profile_name)

        with st.status("Generating documents…", expanded=True) as gen_status:
            status, output = build_resume_and_cover_letter(
                job_id=job.id,
                resume_text=resume_text or "",
                on_progress=lambda msg: st.write(msg),
            )
            if status:
                st.session_state["resume_output"] = output
                gen_status.update(
                    label="Documents ready!",
                    state="complete",
                    expanded=False,
                )
            else:
                st.warning(output)
                st.stop()

    output = st.session_state.get("resume_output", {})

    st.markdown("### 🤖 Generated Documents")
    st.markdown(f"Job: **{job.title}** - {job.company.name}")

    st.download_button(
        "📄 Download Resume",
        output.get("resume", ""),
        file_name="resume.txt",
    )
    st.download_button(
        "📄 Download Cover Letter",
        output.get("cover_letter", ""),
        file_name="cover_letter.txt",
    )

    if st.button("⬅️ Back to Search", key="back_from_generate_resume"):
        st.session_state.pop("generate_resume", None)
        st.session_state.pop("resume_output", None)
        st.rerun()

    st.divider()


# ── LLM response pane ─────────────────────────────────────────────

if st.session_state.get("llm_response"):

    st.markdown("### 🤖 Assistant Response")
    st.markdown(st.session_state["llm_response"])

    if st.button("⬅️ Back to Search", key="back_from_llm_response"):
        st.session_state["llm_response"] = None
        st.rerun()

    st.divider()


# ── Favorites pane ─────────────────────────────────────────────────

if st.session_state.get("show_favorites_pane"):

    st.header("⭐ Your Favorite Jobs")

    profile_name = st.session_state.get("selected_profile", "")
    if not profile_name:
        st.warning("Please select a profile to view favorites.")
    else:
        with Session() as db:
            fav_profile = db.query(Profile).filter(Profile.name == profile_name).first()

            if not fav_profile or not fav_profile.favorite_job_ids:
                st.info("You haven't marked any jobs as favorite yet.")
            else:
                jobs = (
                    db.query(Job)
                    .options(joinedload(Job.company))
                    .filter(Job.job_id.in_(fav_profile.favorite_job_ids))
                    .all()
                )
                show_jobs(jobs, key_prefix="fav", ui=st)

                visible_job_ids_fav = [job.job_id for job in jobs if job.job_id]
                st.session_state["visible_job_ids_fav"] = visible_job_ids_fav

        if st.button("⬅️ Back to Search", key="back_from_favorite"):
            st.session_state.show_favorites_pane = False
            st.session_state["visible_job_ids_fav"] = None
            st.rerun()

        st.divider()


# ── Search button ──────────────────────────────────────────────────

if st.button("🚀 Search Jobs"):
    st.session_state["llm_response"] = None

    # Map UI labels → API values
    countries = get_countries()
    languages = get_languages()

    emp_labels = st.session_state.get("employment_types", [])
    emp_types = ",".join(EMPLOYMENT_TYPE_OPTIONS[l] for l in emp_labels) if emp_labels else None

    exp_labels = st.session_state.get("job_requirements", [])
    exp_types = ",".join(EXPERIENCE_OPTIONS[l] for l in exp_labels) if exp_labels else None

    selected_profile = st.session_state.get("selected_profile", "default")
    p_data = load_profile(selected_profile)

    placeholder = st.empty()

    with st.spinner("Searching…"):
        job_ids = start_job_search(
            keywords=st.session_state.keywords,
            location=st.session_state.location,
            country=countries[st.session_state.country_name],
            language=languages[st.session_state.language_name],
            date_posted=st.session_state.date_posted,
            work_from_home=st.session_state.work_from_home,
            employment_types=emp_types,
            job_requirements=exp_types,
            distance_radius=st.session_state.distance_radius,
            my_latitude=p_data.get("latitude"),
            my_longitude=p_data.get("longitude"),
            max_jobs=st.session_state.max_jobs,
            on_progress=lambda msg: placeholder.info(msg),
        )

    placeholder.empty()
    st.session_state["job_id_list"] = job_ids


# ── Display results ────────────────────────────────────────────────

if st.session_state["job_id_list"]:
    job_id_list = st.session_state["job_id_list"]
    s_profile = st.session_state.get("selected_profile", "default")
    p_data = load_profile(s_profile)
    process_results(job_id_list, p_data, ui=st)


# ── Debug (commented out) ──────────────────────────────────────────
# import debugpy
# if "debugger_active" not in st.session_state:
#     debugpy.listen(("0.0.0.0", 5678))
#     st.session_state["debugger_active"] = True
