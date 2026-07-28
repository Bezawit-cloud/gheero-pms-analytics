import streamlit as st
from config import COLOR_PRIMARY


def inject_custom_css():
    """Global visual polish — call once, near the top of app.py's main()."""
    st.markdown(
        """
        <style>
            html, body, [class*="css"] {
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
                    Roboto, Helvetica, Arial, sans-serif;
            }
            .block-container {
                padding-top: 2rem;
                padding-bottom: 3rem;
            }
            div[data-testid="stMetric"] {
                background: #ffffff;
                border: 1px solid #e6e6e6;
                border-radius: 10px;
                padding: 16px 18px;
                box-shadow: 0 1px 3px rgba(0,0,0,0.05);
            }
            div[data-testid="stMetricLabel"] {
                font-size: 13px;
                color: #6b7280;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.03em;
            }
            div[data-testid="stMetricValue"] {
                font-size: 26px;
                font-weight: 700;
                color: #111827;
            }
            section[data-testid="stSidebar"] {
                background-color: #f7f9fc;
                border-right: 1px solid #e6e6e6;
            }
            h2, h3 {
                margin-top: 0.4rem;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header(title: str, subtitle: str):
    """Renders an enterprise-grade gradient header block."""
    st.markdown(
        f"""
        <div style="background: linear-gradient(90deg, #1f77b4 0%, #2ca02c 100%); padding: 24px; border-radius: 12px; color: white; margin-bottom: 24px;">
            <h1 style="margin: 0; font-size: 26px; font-weight: 700;">{title}</h1>
            <p style="margin: 8px 0 0 0; font-size: 14px; opacity: 0.9;">{subtitle}</p>
        </div>
    """,
        unsafe_allow_html=True,
    )


def render_insight(text: str):
    """Renders a consistently styled 'business insight' callout under a chart."""
    st.markdown(
        f"""
        <div style="background: #f0f7ff; border-left: 4px solid {COLOR_PRIMARY};
                    padding: 12px 16px; border-radius: 6px; margin: 6px 0 22px 0;
                    font-size: 14px; color: #1a1a1a; line-height: 1.5;">
            <strong>💡 Business Insight:</strong> {text}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_risk_badge(risk_score: float):
    """Renders a styled risk badge based on probability threshold."""
    if risk_score >= 0.35:
        st.error(f"**Critical Risk** ({risk_score * 100:.1f}%)")
    elif risk_score >= 0.20:
        st.warning(f"**High Risk** ({risk_score * 100:.1f}%)")
    elif risk_score >= 0.10:
        st.info(f"**Moderate Risk** ({risk_score * 100:.1f}%)")
    else:
        st.success(f"**Low Risk - On Track** ({risk_score * 100:.1f}%)")