import json
import os
import streamlit as st
from load_config import LOAD_LOCALLY

# LOAD_LOCALLY = False

JSON_PATH = "roles.json"


def load_roles():
    if not os.path.exists(JSON_PATH):
        return []
    with open(JSON_PATH, "r") as f:
        data = json.load(f)
        return data.get("internship_position", [])


def save_roles(roles):
    with open(JSON_PATH, "w") as f:
        json.dump({"internship_position": roles}, f, indent=2)


def delete_role(roles, role_to_delete):
    return [role for role in roles if role != role_to_delete]


def manage_internship_roles_tab():
    st.subheader("🎓 Internship Role Manager")

    roles = load_roles()

    new_role = st.text_input("➕ Add a New Role")
    if st.button("Add Role"):
        if not new_role.strip():
            st.warning("Role name cannot be empty.")
        elif new_role in roles:
            st.info("This role already exists.")
        else:
            roles.append(new_role.strip())
            save_roles(roles)
            st.success(f"'{new_role}' added.")
            st.experimental_rerun() if LOAD_LOCALLY else st.rerun()

    # st.divider()
    st.markdown("---")

    st.subheader("📋 Manage Existing Roles")

    if not roles:
        st.info("No roles yet.")
    else:
        for i, role in enumerate(roles):
            col1, col2, col3 = st.columns([5, 1, 1])

            with col1:
                updated_role = st.text_input(f"Edit Role {i + 1}", value=role, key=f"edit_{i}")

            with col2:
                # Align button to the bottom of the input
                st.markdown("<div style='height: 1.9em;'></div>", unsafe_allow_html=True)
                if st.button("💾", key=f"save_{i}", help="Save changes"):
                    if not updated_role.strip():
                        st.warning("Empty names not allowed.", icon="⚠️")
                    elif updated_role != role and updated_role in roles:
                        st.warning("Duplicate role.", icon="⚠️")
                    else:
                        roles[i] = updated_role.strip()
                        save_roles(roles)
                        col1.success("Saved ✅")
                        st.experimental_rerun() if LOAD_LOCALLY else st.rerun()

            with col3:
                st.markdown("<div style='height: 1.9em;'></div>", unsafe_allow_html=True)
                if st.button("🗑️", key=f"delete_{i}", help="Delete this role"):
                    roles = delete_role(roles, role)
                    save_roles(roles)
                    st.success(f"Deleted: {role}")
                    st.experimental_rerun() if LOAD_LOCALLY else st.rerun()
