import streamlit as st

st.title("SaqrSight 🦅")
st.subheader("See Through the Noise")

st.write("Welcome to your graduation project! This is the starting screen.")

# Create a text box
caption = st.text_area("Enter the social media caption here:")

# Create an upload button for images
uploaded_file = st.file_uploader("Upload an image", type=["jpg", "jpeg", "png"])

# Create an analyze button
if st.button("Analyze Post"):
    if caption and uploaded_file is not None:
        st.success("✅ Post received! The AI analysis will go here.")
        st.image(uploaded_file, caption="Uploaded Image", use_column_width=True)
    else:
        st.warning("⚠️ Please provide both a caption and an image.")