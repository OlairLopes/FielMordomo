def _gerenciar_logos():
    st.subheader("Logos do sistema")

    st.markdown("#### Logo do FielMordomo")
    st.caption("Aparece na tela de login e na sidebar do administrador.")

    logo_sis = obter_logo_sistema()
    if logo_sis:
        dados, ext = logo_sis
        st.image(dados, width=200)
        st.caption(f"Formato atual: {ext.upper()}")
    else:
        st.info("Nenhum logo do sistema cadastrado ainda.")

    # Contador para resetar o uploader apos cada envio
    if "logo_sis_counter" not in st.session_state:
        st.session_state["logo_sis_counter"] = 0

    arquivo_sis = st.file_uploader(
        "Enviar logo do FielMordomo",
        type=["png", "jpg", "jpeg", "webp"],
        key=f"upload_logo_sis_{st.session_state['logo_sis_counter']}",
    )
    if arquivo_sis:
        ext = arquivo_sis.name.rsplit(".", 1)[-1].lower()
        salvar_logo_sistema(arquivo_sis.read(), ext)
        st.toast("Logo do sistema salvo!")
        # Incrementa contador para resetar o uploader
        st.session_state["logo_sis_counter"] += 1
        st.rerun()

    st.divider()
    st.markdown("#### Logo por igreja")
    st.caption("Aparece na sidebar apos o login da igreja.")

    df = listar_igrejas()
    if df.empty:
        st.info("Nenhuma igreja cadastrada ainda.")
        return

    opcoes_ig = df.apply(lambda r: f'{r["nome"]} ({r["slug"]})', axis=1).tolist()
    ig_sel    = st.selectbox("Selecione a igreja", opcoes_ig, key="sel_ig_logo")
    idx       = opcoes_ig.index(ig_sel)
    slug      = str(df.iloc[idx]["slug"])

    logo_ig = obter_logo_igreja(slug)
    if logo_ig:
        dados, ext = logo_ig
        st.image(dados, width=200)
        st.caption(f"Formato atual: {ext.upper()}")
    else:
        st.info(f"Nenhum logo cadastrado para {ig_sel}.")

    # Contador especifico por igreja
    counter_key = f"logo_ig_counter_{slug}"
    if counter_key not in st.session_state:
        st.session_state[counter_key] = 0

    arquivo_ig = st.file_uploader(
        f"Enviar logo para: {ig_sel}",
        type=["png", "jpg", "jpeg", "webp"],
        key=f"upload_logo_ig_{slug}_{st.session_state[counter_key]}",
    )
    if arquivo_ig:
        ext = arquivo_ig.name.rsplit(".", 1)[-1].lower()
        salvar_logo_igreja(slug, arquivo_ig.read(), ext)
        st.toast(f"Logo de {ig_sel} salvo!")
        # Incrementa contador para resetar o uploader
        st.session_state[counter_key] += 1
        st.rerun()
