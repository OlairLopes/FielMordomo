from utils.planos import obter_plano, pode_cadastrar_membro, texto_limite, proximo_plano

igreja = st.session_state.get("igreja", {})
plano  = igreja.get("plano", "basico")
p_info = obter_plano(plano)

# Conta apenas membros (nao fornecedores)
qtd_membros = len(df[df["tipo_cadastro"].str.upper() == "MEMBRO"]) if not df.empty and "tipo_cadastro" in df.columns else 0
limite      = p_info["limite_membros"]
bloqueado   = not pode_cadastrar_membro(plano, qtd_membros)

# Indicador de uso
if limite:
    pct = min(100, int((qtd_membros / limite) * 100))
    cor_barra = "#D85A30" if pct >= 90 else ("#F5A623" if pct >= 70 else "#1D9E75")
    st.markdown(f"""
    <div style="background:#f8f9fa;padding:10px 14px;border-radius:8px;margin-bottom:14px">
        <div style="display:flex;justify-content:space-between;font-size:0.85rem;margin-bottom:4px">
            <span><b>Plano {p_info['nome']}:</b> {qtd_membros} de {limite} membros</span>
            <span style="color:{cor_barra};font-weight:600">{pct}%</span>
        </div>
        <div style="background:#e9ecef;height:6px;border-radius:3px;overflow:hidden">
            <div style="background:{cor_barra};height:100%;width:{pct}%"></div>
        </div>
    </div>
    """, unsafe_allow_html=True)
