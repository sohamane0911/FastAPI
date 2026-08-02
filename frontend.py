import streamlit as st
import requests
import base64
import urllib.parse

st.set_page_config(page_title="Simple Social", layout="wide")

# API_URL = "http://127.0.0.1:8000"
API_URL = "https://fastapi-9nfg.onrender.com".rstrip("/")

if 'token' not in st.session_state:
    st.session_state.token = None
if 'user' not in st.session_state:
    st.session_state.user = None


def get_headers():
    if st.session_state.token:
        return {"Authorization": f"Bearer {st.session_state.token}"}
    return {}


def login_page():
    st.title("🚀 Welcome to Simple Social")
    st.markdown("Hello!! Actually it's safe, but still use your secondary or tertiary mail guys. And I hope you like it")

    tab1, tab2 = st.tabs(["Login", "Sign Up"])

    with tab1:
        login_username = st.text_input("Username:")
        login_password = st.text_input("Password:", type="password", key="login_pass")

        if st.button("Login", type="primary", use_container_width=True):
            if login_username and login_password:
                login_data = {"username": login_username, "password": login_password}

                try:
                    response = requests.post(f"{API_URL}/login", data=login_data)

                    if response.status_code == 200:
                        st.session_state.token = response.json()["access_token"]
                        user_response = requests.get(f"{API_URL}/users/me", headers=get_headers())

                        if user_response.status_code == 200:
                            st.session_state.user = user_response.json()
                            st.rerun()
                        else:
                            st.error("Failed to fetch user info")
                    else:
                        # Safely extract error message
                        try:
                            err = response.json().get("detail", "Invalid credentials!")
                        except Exception:
                            err = f"Server Error ({response.status_code}): {response.text or 'No response body'}"
                        st.error(err)

                except requests.exceptions.RequestException as e:
                    st.error(f"Connection error: {e}")
            else:
                st.warning("Please enter credentials.")

    with tab2:
        reg_username = st.text_input("Choose Username:")
        reg_email = st.text_input("Email:")
        reg_password = st.text_input("Choose Password:", type="password", key="reg_pass")

        if st.button("Sign Up", type="secondary", use_container_width=True):
            if reg_username and reg_email and reg_password:
                signup_data = {"username": reg_username, "email": reg_email, "password": reg_password}

                try:
                    response = requests.post(f"{API_URL}/register", json=signup_data)

                    if response.status_code in [200, 201]:
                        st.success("Account created! You can now Login.")
                    else:
                        # SAFE PARSING: Prevent crash when backend returns HTML or non-JSON text
                        try:
                            error_detail = response.json().get("detail", "Registration failed")
                        except Exception:
                            error_detail = f"Server returned status {response.status_code}: {response.text or 'Empty response'}"

                        st.error(f"Registration failed: {error_detail}")

                except requests.exceptions.RequestException as e:
                    st.error(f"Connection error: {e}")
            else:
                st.warning("Please fill out all fields.")


def upload_page():
    st.title("📸 Share Something")

    uploaded_file = st.file_uploader("Choose media", type=['png', 'jpg', 'jpeg', 'mp4', 'avi', 'mov', 'mkv', 'webm'])
    caption = st.text_area("Caption:", placeholder="What's on your mind?")

    if uploaded_file and st.button("Share", type="primary"):
        with st.spinner("Uploading..."):
            files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
            data = {"caption": caption, "is_public": True}
            response = requests.post(f"{API_URL}/upload", files=files, data=data, headers=get_headers())

            if response.status_code == 200:
                st.success("Posted!")
                st.rerun()
            else:
                st.error(f"Upload failed: {response.text}")


def encode_text_for_overlay(text):
    if not text: return ""
    base64_text = base64.b64encode(text.encode('utf-8')).decode('utf-8')
    return urllib.parse.quote(base64_text)


def create_transformed_url(original_url, transformation_params, caption=None):
    if caption:
        encoded_caption = encode_text_for_overlay(caption)
        text_overlay = f"l-text,ie-{encoded_caption},ly-N20,lx-20,fs-100,co-white,bg-000000A0,l-end"
        transformation_params = text_overlay

    if not transformation_params:
        return original_url

    parts = original_url.split("/")
    if len(parts) < 5: return original_url

    file_path = "/".join(parts[4:])
    base_url = "/".join(parts[:4])
    return f"{base_url}/tr:{transformation_params}/{file_path}"


def feed_page():
    st.title("🏠 Feed")
st.markdown("Welcome guyzz!!! Glad to see you here😊. This is just an alpha phase. So make some posts and check your feed")

    response = requests.get(f"{API_URL}/feed", headers=get_headers())
    if response.status_code == 200:
        posts = response.json()  # Backend returns a direct list now

        if not posts:
            st.info("No posts yet! Be the first to share something.")
            return

        for post in posts:
            st.markdown("---")
            is_owner = (post['user_id'] == st.session_state.user['id'])

            col1, col2 = st.columns([4, 1])
            with col1:
                st.markdown(f"**{post['username']}** • {post['created_at'][:10]}")
            with col2:
                if is_owner:
                    # Endpoint URL updated to match backend `/delete_post/{post_id}`
                    if st.button("🗑️", key=f"delete_{post['id']}", help="Delete post"):
                        del_response = requests.delete(f"{API_URL}/delete_post/{post['id']}", headers=get_headers())
                        if del_response.status_code == 200:
                            st.success("Post deleted!")
                            st.rerun()
                        else:
                            st.error("Failed to delete post!")

            caption = post.get('caption', '')
            if post['file_type'].startswith('image'):
                uniform_url = create_transformed_url(post['url'], "", caption)
                st.image(uniform_url, width=300)
            else:
                uniform_video_url = create_transformed_url(post['url'], "w-400,h-200,cm-pad_resize,bg-blurred")
                st.video(uniform_video_url)
                st.caption(caption)
            st.markdown("")
    else:
        st.error("Failed to load feed")


if st.session_state.user is None:
    login_page()
else:
    st.sidebar.title(f"👋 Hi {st.session_state.user['username']}!")

    if st.sidebar.button("Logout"):
        st.session_state.user = None
        st.session_state.token = None
        st.rerun()

    st.sidebar.markdown("---")
    page = st.sidebar.radio("Navigate:", ["🏠 Feed", "📸 Upload"])

    if page == "🏠 Feed":
        feed_page()
    else:
        upload_page()
