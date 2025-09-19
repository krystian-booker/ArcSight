from flask import Flask, render_template

app = Flask(__name__, template_folder='templates', static_folder='static')

@app.route('/')
def dashboard():
    return render_template('index.html')

@app.route('/config')
def config():
    return render_template('config.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
