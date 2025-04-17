import os
import re
import time
import json
import threading
from datetime import datetime
from urllib.parse import urljoin
from collections import defaultdict
from bs4 import BeautifulSoup
from markdownify import markdownify as md_convert
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

BASE_OUTPUT_FOLDER = "RAG_Collection"
MAX_LINK_LEVEL = 40
MAX_PAGES_PER_PRODUCT = 10000

PRODUCT_URL_PREFIXES = {
    "Communications_Cloud": ["id=ind.comms", "/products/communications"],
    "Sales_Cloud": ["id=sales", "/products/sales"],
    "Service_Cloud": ["id=service", "/products/service"],
    "Experience_Cloud": ["id=experience", "/products/experience"],
    "Marketing_Cloud": ["id=mktg", "/products/marketing"],
    "Data_Cloud": ["id=data", "/products/datacloud"],
    "Platform": ["id=platform", "/products/platform"],
    "Agentforce": ["id=ai", "ai.generative_ai"],
}

START_LINKS = [
    {
        "product": "Sales_Cloud",
        "urls": [
            "https://help.salesforce.com/s/articleView?id=sales.sales_get_started.htm&type=5",
            "https://help.salesforce.com/s/articleView?id=sales.sales_core.htm&type=5",
            "https://help.salesforce.com/s/articleView?id=sales.sales_core_basics.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_setup_eci.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_partner_considerations.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_setup_parent.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_template_prerequisites.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_measures_eci_guidelines.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_measures_considerations.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_setup_assign_perms.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_sandbox.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_measures_examples.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_setup_eci_sandbox_setup.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_measures_overview.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_compatibility.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_milestone_measure.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_rollout.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_create_program_template.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_overview.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_milestone_composite.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_notifications.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_lite_limits.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_analytics_considerations.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_drives_outcomes_parent.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_outcomes.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.ci_setup_features.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_partner_analytics.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_measures_create_parent.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_program_complete.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_analytics_completion_statuses.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_programs_overview.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_setup_einstein_coach.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_partner.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_assignments_guidelines.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_template_parent.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_build_parent.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_languages.htm&type=5",
            "https://help.salesforce.com/articleView?id=release-notes.rn_sales.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_partner_components.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_feedback_request_take.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_partner_create.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_limits.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.ci_setup_assign_perm_sets.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_analytics_refresh.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_programs_exercise_types_reference.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_content_guidelines.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_analytics.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.access_enablement_analytics.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_roles.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_clone_program.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_content.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_permissions.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_feedback_request_parent.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_milestone_parent.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_feedback_request_setup.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_programs_self_enroll.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.automated_assignment_flow.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_package.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_confetti.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_programs_assign.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_program_publish.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_program_unpublish.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_programs_published_edit.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.automated_assignment_apex.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_reports.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_program_plan.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_package_uninstall.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_content_rich_text.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_content_image.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_content_link_video.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_content_contributor.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_setup_considerations.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_lite_permissions.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_feedback_request_program.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_content_program_builder.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_feedback_request_survey.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_programs_unassign.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_einstein_coach_parent.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_add_einstein_coach.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_clone_measure.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_measures_create.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_lite_analytics.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_data_model.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_measures_access.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.sales_core_artificial_intelligence.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.ci_start.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.call_coaching.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_publish_assign_parent.htm&type=5"
            "https://help.salesforce.com/articleView?id=sales.enablement_unpublish_unassign.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.eci_connector_get_started.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.eci_conv_signals.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.call_coaching_setup.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.eci_gen_insights.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.ci_related_record_voice.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.ci_related_records.htm&type=5",
            "https://help.salesforce.com/articleView?id=release-notes.rn_employee_service_employee_enablement_program.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.automated_assignment_rest_api.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.ci_related_record_parent.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_deploy.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_custom_items_overview.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_lite.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.automated_program_assignment.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_take_einstein_coach_exercise.htm&type=5",
            "https://help.salesforce.com/articleView?id=release-notes.rn_sales_programs_view_analytics_for_sales_leaders.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.call_coaching_recording_providers.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.eci_call_summaries.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.ci_considerations.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.access_einstein_coach_guidance_center.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_feedback_request_survey_sharing.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.filter_enablement_program.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.eci_call_explorer.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.eci_add_signals.htm&type=5",
            "https://help.salesforce.com/articleView?id=release-notes.rn_sales_programs_enablement_toggle.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.ci_security.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.eci_add_insight_page_layout.htm&type=5",
            "https://help.salesforce.com/articleView?id=release-notes.rn_enablement_guidance.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.call_coaching_setup_insights.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.call_coaching_setup_recording_providers.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.eci_connector_variable_phone_number.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.ci_setup_enable.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.eci_summary_page_layout.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.eci_add_call_explorer.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.eci_connector_fix.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.sales_trailhead_learning_map.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.eci_connector_considerations.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.video_teams_security.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.enablement_einstein_coach_considerations.htm&type=5",
            "https://help.salesforce.com/articleView?id=release-notes.rn_einstein_feature_overview.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.hvs_considerations_eci.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.hvs_setup_configure_ci.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.ci_run_readiness_assessor.htm&type=5",
            "https://help.salesforce.com/articleView?id=release-notes.rn_sales_eci_ai_lang_support.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.eci_connector_start.htm&type=5",
            "https://help.salesforce.com/articleView?id=release-notes.rn_sales_eci_top.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.eci_config_gen_insights.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.eci_gen_conv_insights_considerations.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.video_teams_parent.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.ci_related_record_troubleshooting.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.sales_job_landing_build_develop_teams.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.eci_connector_integration_user.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.einstein_copilot_for_sales.htm&type=5",
            "https://help.salesforce.com/articleView?id=release-notes.rn_sales_eci_explorer_flow.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.eci_connector_disable.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.eci_sales_signals_considerations.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.einstein_sales_activity_reporting_overview.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.ci_speaker_separation.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.opp_stage_suggestion_enable.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.video_zoom_parent.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.hvs_considerations.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.hvs_reports_reports_dashboards_overview.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.eci_connector_enable.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.eci_call_explorer_considerations.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.hvs_setup_assign.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.eci_call_summary_considerations.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.eci_connector_install_package.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.ci_setup_recording_providers_video.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.eci_connector_manage_excluded.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.eci_connector_configure.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.eci_connector_launch.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.pipeline_inspection_setup_deal_insights.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.einstein_sales_activity_reporting_considerations.htm&type=5",
            "https://help.salesforce.com/articleView?id=release-notes.rn_enablement.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.sales_productivity.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.pipeline_inspection_more_features.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.video_zoom_use_data.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.video_zoom_use_setup_user.htm&type=5",
            "https://help.salesforce.com/articleView?id=sales.iag_site_limitations.htm&type=5",

        ]
    },
    {
        "product": "Service_Cloud",
        "urls": [
            "https://help.salesforce.com/s/articleView?id=service.service_cloud.htm&type=5"
            "https://help.salesforce.com/s/articleView?id=service.support_admins_intro.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.embedded_chat_channel_menu.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.livemessage_intro.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.voice_about.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.es_set_up_voice_calls.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.voice_troubleshooting_tips.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.support_channels.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.support_admins_intro.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.console_lex_update_service_setup_assistant.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.service_cloud_def.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.support_service_channels.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.admin_supportsetup.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.svc_intro.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.knowledge_whatis.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.es_set_up_knowledge.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.support_admins_intro.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.support_deflection.htm&type=5",
            "https://help.salesforce.com/articleView?id=release-notes.rn_comm_knowledge_articles.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.einstein_service_intro.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.einstein_replies_intro.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.es_employee_service_setup.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.cc_service_what_is.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.einstein_generative_ai_grounding_setup.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.messaging_apple_plan.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.service_data_usage.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.knowledge_creation_map_responses.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.bots_service_intro.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.reply_recs_generative_ai_enable.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.knowledge_creation_usage_and_tracking.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.knowledge_similarity_setup.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.knowledge_creation_enable.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.knowledge_creation_parent.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.knowledge_creation_set_up.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.knowledge_creation_glossary.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.knowledge_creation_learn_knowledge_fields.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.knowledge_creation_example.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.knowledge_creation_parent_learn.htm&type=5",
            "https://help.salesforce.com/articleView?id=release-notes.rn_alert_agents_to_KA_with_einstein_knowledge_creation_async_notification.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.knowledge_creation_access.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.knowledge_creation_data_cloud_knowledge_similarity.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.knowledge_creation_use.htm&type=5",
            "https://help.salesforce.com/articleView?id=release-notes.rn_salesforce_knowledge.htm&type=5",
            "https://help.salesforce.com/articleView?id=release-notes.rn_revise_ka_quickly_with_einstein_knowledge_edits.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.support_admins_intro.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.msj_intro.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.cases_intro.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.contact_request.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.admin_supportsetup.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.scm_overview.htm&type=5",
            "https://help.salesforce.com/articleView?id=release-notes.rn_msj_ga.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.contact_request_considerations.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.service_insights_enable_service_features.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.service_cloud.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.ifs_considerations.htm&type=5",
            "https://help.salesforce.com/articleView?id=service.service_intelligence_considerations.htm&type=5",
            
        ]
    },
    {
        "product": "Agentforce",
        "urls": [
            "https://help.salesforce.com/s/articleView?id=ai.generative_ai.htm&type=5",
            "https://help.salesforce.com/s/articleView?id=ai.copilot_intro.htm&type=5"
        ]
    },
    {
        "product": "Platform",
        "urls": [
            "https://help.salesforce.com/s/articleView?id=platform.platform_automation.htm&type=5",
            "https://help.salesforce.com/s/articleView?id=platform.users_manage_access.htm&language=en_US&type=5",
            "https://help.salesforce.com/s/articleView?id=platform.ls_overview.htm&language=en_US&type=5",
            "https://help.salesforce.com/s/articleView?id=platform.extend_click_intro.htm&language=en_US&type=5",
            "https://help.salesforce.com/s/articleView?id=platform.trialforce_why_use.htm&language=en_US&type=5",
            "https://help.salesforce.com/s/articleView?id=platform.extend_code_overview.htm&language=en_US&type=5",
            "https://help.salesforce.com/s/articleView?id=platform.deploy_sandboxes_parent.htm&language=en_US&type=5",
            "https://help.salesforce.com/s/articleView?id=platform.devops_center_overview.htm&language=en_US&type=5",
            "https://help.salesforce.com/s/articleView?id=platform.devops_center_setup.htm&language=en_US&type=5"
        ]
    },
    {
        "product": "Communications_Cloud",
        "urls": ["https://help.salesforce.com/s/articleView?id=ind.comms_communications_and_media_clouds_34031.htm&type=5"]
    },
    {
        "product": "Experience_Cloud",
        "urls": ["https://help.salesforce.com/s/articleView?id=experience.networks_overview.htm&type=5"]
    },
    {
        "product": "Data_Cloud",
        "urls": ["https://help.salesforce.com/s/articleView?id=data.c360_a_data_cloud.htm&type=5"]
    },
    {
        "product": "Marketing_Cloud",
        "urls": ["https://help.salesforce.com/s/articleView?id=mktg.mktg_main.htm&type=5"]
    }
]

IGNORE_LINK_TEXTS = ["Refresh", "Close", "×", "Sorry to interrupt"]
IGNORE_HREF_PREFIXES = ["javascript:", "mailto:"]
IGNORE_LINKS = [
    "https://help.salesforce.com/s?language=en_US",
    "/s/?language=en_US",
    "/s/products?language=en_US"
]

visited = {}
crawl_graph = {"nodes": set(), "edges": set()}
logged_ignored_links = set()
product_md_counts = defaultdict(int)

visited_lock = threading.Lock()
graph_lock = threading.Lock()
ignored_lock = threading.Lock()

def log_links(folder, base, suffix, links):
    path = os.path.join(folder, f"{base}_{suffix}.log")
    with open(path, "w", encoding="utf-8") as f:
        for link in links:
            f.write(f"{link['text']} -> {link['href']}\n")

def dismiss_cookie_popup(driver):
    try:
        reject_button = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Do Not Accept']"))
        )
        reject_button.click()
        print("✅ Cookie popup dismissed.")
        time.sleep(1)
    except TimeoutException:
        print("⚠️ No cookie popup to dismiss.")

def clean_cookie_content(soup):
    cookie_keywords = ["cookie", "consent", "accept all", "do not accept", "privacy statement", "cookie settings"]
    for tag in soup.find_all(True):
        if any(kw in tag.get_text().lower() for kw in cookie_keywords):
            tag.decompose()
    return soup

def sanitize_filename(url):
    return re.sub(r'[^a-zA-Z0-9-_\.]', '_', re.sub(r'^https?://', '', url))[:200]

ALLOWED_DOMAINS = [
    "https://help.salesforce.com",
    "https://developer.salesforce.com",
    "https://trailhead.salesforce.com",
    "https://salesforce.com/docs",
]

def should_ignore_link(link):
    text = link.get("text", "").strip().lower()
    href = link.get("href", "").strip()
    if not href or any(href.startswith(prefix) for prefix in IGNORE_HREF_PREFIXES):
        return True
    if text in [t.lower() for t in IGNORE_LINK_TEXTS]:
        return True
    if href.lower() in [ignore.lower() for ignore in IGNORE_LINKS]:
        return True
    if not any(href.startswith(domain) for domain in ALLOWED_DOMAINS):
        return True
    return False

def log_ignored_link(origin_url, link):
    if not link["href"].startswith("https://help.salesforce.com"):
        key = (origin_url, link["text"], link["href"])
        with ignored_lock:
            if key not in logged_ignored_links:
                logged_ignored_links.add(key)
                path = os.path.join(BASE_OUTPUT_FOLDER, "ignored_links.log")
                with open(path, "a", encoding="utf-8") as f:
                    f.write(f"From: {origin_url} | Text: {link['text']} | Href: {link['href']}\n")

def log_duplicate_link(link, product, current_source_url):
    path = os.path.join(BASE_OUTPUT_FOLDER, "duplicate_links.log")
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"Duplicate Link: {link['href']}\n")
        f.write(f"First Found: {link['first_product']} from {link['first_source']} ({link['first_filename']})\n")
        f.write(f"Found Again: {product} from {current_source_url}\n\n")

def save_file(folder, filename, content):
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def export_crawl_graph():
    with open(os.path.join(BASE_OUTPUT_FOLDER, "link_graph.json"), "w", encoding="utf-8") as f:
        json.dump({
            "nodes": list(crawl_graph["nodes"]),
            "edges": [list(e) for e in crawl_graph["edges"]]
        }, f, indent=2)

def count_md_files_per_product():
    summary_path = os.path.join(BASE_OUTPUT_FOLDER, "summary.log")
    with open(summary_path, "w") as f:
        print("\n📊 Crawl Summary:")
        f.write("Crawl Summary:\n")
        for product in sorted(product_md_counts):
            count = product_md_counts[product]
            print(f"- {product}: {count} markdown files")
            f.write(f"- {product}: {count} markdown files\n")

def create_markdown(content_html, tag, depth, source_url, title_override=None):
    soup = BeautifulSoup(content_html, "html.parser")
    soup = clean_cookie_content(soup)
    content_html = str(soup)

    md = md_convert(content_html, heading_style="ATX")
    title = title_override or (soup.title.get_text().strip() if soup.title else "")
    h1 = soup.find("h1")
    main_heading = h1.get_text().strip() if h1 else ""
    yaml = f"""---
title: "{title or main_heading}"
date: "{datetime.now().strftime('%Y-%m-%d')}"
tag: "{tag}"
category: "Product Documentation: {tag}"
toc: true
depth_level: {depth}
source_url: "{source_url}"
---

"""
    headings = re.findall(r"^(#+)\s+(.*)", md, re.MULTILINE)
    toc = "\n".join(
        "  " * (len(h[0]) - 1) + f"- [{h[1]}](#{re.sub(r'[^a-zA-Z0-9 ]', '', h[1]).lower().replace(' ', '-')})"
        for h in headings
    )
    return yaml + f"## Table of Contents\n\n{toc}\n\n" + md

def extract_links_from_html(html, origin):
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        link = {"text": a.get_text().strip(), "href": urljoin(origin, a["href"])}
        if not should_ignore_link(link):
            links.append(link)
        else:
            log_ignored_link(origin, link)
    return links

def detect_page_type(url):
    if "help.salesforce.com/s/articleView" in url:
        return 1
    elif "developer.salesforce.com/docs" in url:
        return 2
    elif "help.salesforce.com/s/products" in url:
        return 3
    return 0

def handle_type_1(driver, url, product, folder, depth, source_url):
    try:
        driver.get(url)
        dismiss_cookie_popup(driver)
        time.sleep(2)
        try:
            element = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'content with-toc')]//content"))
            )
        except:
            js_script = """
                const host = document.querySelector("#maincontent > doc-xml-content");
                if (host && host.shadowRoot) {
                  const container = host.shadowRoot.querySelector("doc-content-layout > doc-content");
                  if (container && container.shadowRoot) {
                    return container.shadowRoot.querySelector("div");
                  }
                }
                return null;
            """
            element = driver.execute_script(js_script)
            if not element:
                print("Type 1: Could not extract content.")
                return [], ""

        html = element.get_attribute("innerHTML")
        base = f"output_{sanitize_filename(url)}"
        md = create_markdown(html, product, depth, source_url)
        save_file(folder, f"{base}.md", md)
        product_md_counts[product] += 1  # ✅ Count only successful save

        main_links = extract_links_from_html(html, url)
        log_links(folder, base, "main" if main_links else "main_failed", main_links)
        return main_links, base

    except Exception as e:
        print(f"[Type 1 Error] {url} — {e}")
        return [], ""

def extract_shadow_nav_links(driver, url):
    try:
        links = driver.execute_script("""
            const tree = document.querySelector('dx-tree');
            if (!tree || !tree.shadowRoot) return [];

            const tiles = tree.shadowRoot.querySelectorAll('dx-tree-tile');
            const links = [];

            tiles.forEach(tile => {
                const shadow = tile.shadowRoot;
                if (!shadow) return;
                const a = shadow.querySelector('a[href]');
                if (a) {
                    links.push({
                        text: a.innerText.trim(),
                        href: a.href
                    });
                }
            });

            return links;
        """)
        return links
    except Exception as e:
        print(f"⚠️ JS sidebar extract failed on {url}: {str(e).splitlines()[0]}")
        return []

def handle_type_2(driver, url, product, folder, depth, source_url):
    try:
        driver.get(url)
        dismiss_cookie_popup(driver)
        time.sleep(2)

        # Legacy iframe layout
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        iframe_names = [f.get_attribute("name") for f in iframes]
        if "NavFrame" in iframe_names:
            print(f"🧓 Using legacy DevDoc frame logic for: {url}")

            driver.switch_to.frame("NavFrame")
            nav_links = extract_links_from_html(driver.page_source, url)
            driver.switch_to.default_content()

            content_links = []
            for link in nav_links:
                href = link["href"]
                driver.switch_to.frame("BodyFrame")
                driver.get(href)
                time.sleep(2)
                try:
                    element = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.ID, "body"))
                    )
                    html = element.get_attribute("innerHTML")
                    base = f"output_{sanitize_filename(href)}"
                    md = create_markdown(html, product, depth + 1, href)
                    save_file(folder, f"{base}.md", md)
                    product_md_counts[product] += 1  # ✅ Count only successful save
                    links = extract_links_from_html(html, href)
                    log_links(folder, base, "main" if links else "main_failed", links)
                    content_links += links
                except Exception as inner_e:
                    print(f"[Type 2 legacy error] {href} — {inner_e}")
                driver.switch_to.default_content()
            return content_links, ""

        # Modern dev docs
        print(f"🆕 Modern DevDoc: extracting <a> and sidebar: {url}")
        html = driver.page_source
        base = f"output_{sanitize_filename(url)}"
        md = create_markdown(html, product, depth, source_url)
        save_file(folder, f"{base}.md", md)
        product_md_counts[product] += 1  # ✅ Count only successful save

        page_links = driver.execute_script("""
            return Array.from(document.querySelectorAll('a[href]')).map(a => ({
                text: a.innerText.trim(),
                href: a.href
            }));
        """)
        sidebar_links = extract_shadow_nav_links(driver, url)
        combined = sidebar_links + page_links

        filtered_links = []
        for link in combined:
            if not should_ignore_link(link):
                filtered_links.append(link)
            else:
                log_ignored_link(url, link)

        log_links(folder, base, "main" if filtered_links else "main_failed", filtered_links)
        return filtered_links, base

    except Exception as e:
        print(f"[Type 2 Error] {url} — {e}")
        return [], ""

def handle_type_3(driver, url, product, folder, depth, source_url):
    try:
        driver.get(url)
        dismiss_cookie_popup(driver)
        time.sleep(2)

        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")
        link_blocks = soup.find_all("a", href=True)

        links = []
        for a in link_blocks:
            href = urljoin(url, a["href"])
            text = a.get_text().strip()
            link = {"text": text, "href": href}
            if not should_ignore_link(link):
                links.append(link)
            else:
                log_ignored_link(url, link)

        base = f"output_{sanitize_filename(url)}"
        title = soup.title.get_text().strip() if soup.title else f"{product} Landing"
        content_md = create_markdown(
            "".join([f"<li><a href='{l['href']}'>{l['text']}</a></li>" for l in links]),
            product, depth, source_url, title_override=title
        )
        save_file(folder, f"{base}.md", content_md)
        product_md_counts[product] += 1  # ✅ Count only successful save

        log_links(folder, base, "main" if links else "main_failed", links)
        return links, base

    except Exception as e:
        print(f"[Type 3 Error] {url} — {e}")
        return [], ""

def detect_page_type(url):
    if "help.salesforce.com/s/articleView" in url:
        return 1
    elif "developer.salesforce.com/docs" in url:
        return 2
    elif "help.salesforce.com/s/products" in url:
        return 3
    return 0

def process_link_bfs(product_info):
    product = product_info["product"]
    urls = product_info.get("urls", [])
    folder = os.path.join(BASE_OUTPUT_FOLDER, product.replace(" ", "_"))
    os.makedirs(folder, exist_ok=True)

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=webdriver.ChromeOptions())
    queue_by_depth = defaultdict(list)

    for start_url in urls:
        with visited_lock:
            visited[start_url] = {
                "product": product,
                "source_url": start_url,
                "filename": f"output_{sanitize_filename(start_url)}.md"
            }
        queue_by_depth[0].append((start_url, start_url))

    try:
        for depth in range(MAX_LINK_LEVEL + 1):
            urls_at_depth = queue_by_depth[depth]
            if not urls_at_depth:
                continue
            print(f"\n📦 {product}, Depth {depth} – {len(urls_at_depth)} pages to scrape")
            for idx, (url, src) in enumerate(urls_at_depth, start=1):
                if product_md_counts[product] >= MAX_PAGES_PER_PRODUCT:
                    print(f"🛑 {product} reached max page limit ({MAX_PAGES_PER_PRODUCT}) — stopping early.")
                    return
                print(f"✅ {product}, Depth {depth} – {idx}/{len(urls_at_depth)}")

                page_type = detect_page_type(url)
                if page_type == 1:
                    links, _ = handle_type_1(driver, url, product, folder, depth, src)
                elif page_type == 2:
                    links, _ = handle_type_2(driver, url, product, folder, depth, src)
                elif page_type == 3:
                    links, _ = handle_type_3(driver, url, product, folder, depth, src)
                else:
                    print(f"❌ Unknown page type for URL: {url}")
                    continue

                with graph_lock:
                    crawl_graph["nodes"].add(url)
                    for link in links:
                        crawl_graph["nodes"].add(link["href"])
                        crawl_graph["edges"].add((url, link["href"]))

                allowed_prefixes = PRODUCT_URL_PREFIXES.get(product, [])

                for link in links:
                    href = link["href"]
                    if not any(prefix in href for prefix in allowed_prefixes):
                        continue
                    if not any(href.startswith(domain) for domain in ALLOWED_DOMAINS):
                        continue

                    with visited_lock:
                        if href in visited:
                            log_duplicate_link({
                                "href": href,
                                "first_product": visited[href]["product"],
                                "first_source": visited[href]["source_url"],
                                "first_filename": visited[href]["filename"]
                            }, product, url)
                            continue

                        visited[href] = {
                            "product": product,
                            "source_url": url,
                            "filename": f"output_{sanitize_filename(url)}.md"
                        }

                    if depth < MAX_LINK_LEVEL:
                        queue_by_depth[depth + 1].append((href, url))

                product_md_counts[product] += 1
    finally:
        driver.quit()

def summarize_md_counts():
    summary_counts = defaultdict(int)
    print(f"\n🔍 Scanning '{BASE_OUTPUT_FOLDER}' for markdown files...")

    for product_dir in os.listdir(BASE_OUTPUT_FOLDER):
        full_path = os.path.join(BASE_OUTPUT_FOLDER, product_dir)
        if os.path.isdir(full_path):
            md_files = [
                f for f in os.listdir(full_path)
                if os.path.isfile(os.path.join(full_path, f)) and f.endswith('.md')
            ]
            summary_counts[product_dir] = len(md_files)

    summary_lines = ["\n📊 Crawl Summary (based on saved .md files):"]
    for product, count in sorted(summary_counts.items()):
        summary_lines.append(f"  - {product}: {count} markdown files")

    summary_output = "\n".join(summary_lines)
    print(summary_output)

    with open(os.path.join(BASE_OUTPUT_FOLDER, "summary.log"), "w", encoding="utf-8") as f:
        f.write(summary_output)

def main():
    threads = []
    for info in START_LINKS:
        t = threading.Thread(target=process_link_bfs, args=(info,))
        t.start()
        threads.append(t)
    for t in threads:
        t.join()
    export_crawl_graph()
    summarize_md_counts()

if __name__ == "__main__":
    main()
