import os
from dotenv import load_dotenv
from flask import Flask, render_template, send_file, url_for
from flask_httpauth import HTTPBasicAuth
from nest import Nest
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()

app = Flask(__name__)
auth = HTTPBasicAuth()

users = {
    user.split(";")[0]: generate_password_hash(user.split(";")[1])
    for user in os.environ.get("USERS", "").split(",")
}

nest = Nest()


@auth.verify_password
def verify_password(username, password):
    if username in users:
        return check_password_hash(users[username], password)
    return False


@app.route('/')
@auth.login_required
def index():
    home_data = nest.get_home_data()
    if 'error' in home_data:
        pass  # TODO: Render an error page
    for index, device in enumerate(home_data.get('devices', [])):
        clips_path = os.path.join('clips', device['id'])
        if not os.path.exists(clips_path):
            os.makedirs(clips_path)
        clips = os.listdir(clips_path)
        home_data['devices'][index]['clips'] = {}
        for clip in clips:
            if clip.endswith('.txt'):
                clip_id = clip[:-4]  # Remove .txt
                clip_path = os.path.join(clips_path, clip)
                with open(clip_path, 'r') as f:
                    text = f.read().strip()
                split = text.split('\n')
                start_date = split[0].strip()
                end_date = split[1].strip()
                immune = "IMMUNE" in text
                duration = int(float(end_date) - float(start_date))
                if clip_id not in home_data['devices'][index]['clips']:
                    home_data['devices'][index]['clips'][clip_id] = {}
                home_data['devices'][index]['clips'][clip_id]['start_date'] = start_date
                home_data['devices'][index]['clips'][clip_id]['end_date'] = end_date
                home_data['devices'][index]['clips'][clip_id]['duration'] = duration
                home_data['devices'][index]['clips'][clip_id]['immune'] = immune
            elif clip.endswith('.mp4'):
                clip_id = clip[:-4]  # Remove .mp4
                if clip_id not in home_data['devices'][index]['clips']:
                    home_data['devices'][index]['clips'][clip_id] = {}
                home_data['devices'][index]['clips'][clip_id]['video'] = clip
                print(f"Found video clip: {clip} for device {device['id']}")
            elif clip.endswith('.jpg'):
                clip_id = clip[:-4]  # Remove .jpg
                if clip_id not in home_data['devices'][index]['clips']:
                    home_data['devices'][index]['clips'][clip_id] = {}
                home_data['devices'][index]['clips'][clip_id]['thumbnail'] = clip
                print(f"Found thumbnail: {clip} for device {device['id']}")
    print(home_data)
    return render_template('index.html', user=auth.current_user(), home_data=home_data)


@app.route('/clip/<device_id>/<filename>')
@auth.login_required
def clip(device_id, filename):
    clips_path = os.path.join('clips', device_id)
    file_path = os.path.join(clips_path, filename)
    print(f"Serving clip: {file_path}")
    if os.path.exists(file_path):
        return send_file(file_path)
    else:
        return "File not found", 404


@app.route('/clip_player/<device_id>/<filename>')
@auth.login_required
def clip_player(device_id, filename):
    source_url = url_for('clip', device_id=device_id, filename=filename)

    return render_template('clip_player.html',
                           source_url=source_url)


@app.route('/delete_clip/<device_id>/<clip_id>')
@auth.login_required
def delete_clip(device_id, clip_id):
    clips_path = os.path.join('clips', device_id)
    # Remove all files that start with the clip_id and have the correct extension
    for ext in ('.mp4', '.jpg', '.txt'):
        for fname in os.listdir(clips_path):
            if fname.endswith(ext) and fname[:-len(ext)] == clip_id:
                os.remove(os.path.join(clips_path, fname))
    return "Clip deleted successfully", 200


@app.route('/mark_immune/<device_id>/<clip_id>')
@auth.login_required
def mark_immune(device_id, clip_id):
    clips_path = os.path.join('clips', device_id)
    # Find the .txt file that matches the clip_id
    text_file = None
    for fname in os.listdir(clips_path):
        if fname.endswith('.txt') and fname[:-4] == clip_id:
            text_file = os.path.join(clips_path, fname)
            break
    if text_file and os.path.exists(text_file):
        with open(text_file, 'r') as f:
            content = f.read().strip()
        immune = "IMMUNE" in content
        with open(text_file, 'w') as f:
            if immune:
                f.write(content.replace("IMMUNE", ""))
            else:
                f.write(content + "\nIMMUNE")
        return "Clip marked as immune" if not immune else "Clip marked as not immune", 200
    else:
        return "Clip not found", 404


@app.route('/batch_delete/<device_id>')
@auth.login_required
def batch_delete(device_id):
    # Delete all clips for the specified device unless they are marked as immune
    clips_path = os.path.join('clips', device_id)
    if not os.path.exists(clips_path):
        return "No clips found for this device", 404

    for fname in os.listdir(clips_path):
        if fname.endswith('.txt'):
            clip_id = fname[:-4]
            text_file = os.path.join(clips_path, fname)
            with open(text_file, 'r') as f:
                content = f.read().strip()
            if "IMMUNE" not in content:
                # Remove all files for this clip_id
                for ext in ('.mp4', '.jpg', '.txt'):
                    target = os.path.join(clips_path, f"{clip_id}{ext}")
                    if os.path.exists(target):
                        os.remove(target)
                        print(f"Deleted {target} for device {device_id}")
    return "Batch delete completed", 200


if __name__ == '__main__':
    app.run()
