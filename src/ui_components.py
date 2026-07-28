import streamlit as st


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