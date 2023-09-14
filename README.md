# Arma 3 Discord Bot
### Features
* ✅ Displaying server status with a list of players
* ✅ Command to restart the server
* ✅ Primitive administration system

### Requirements
* Python >= 3.8

### Deployment

1. Create virtual environment
```
python -m venv venv
```
2. Activate virtual environment
```
source ./venv/bin/activate
```
3. Install required packages
```
pip install -r requirements.txt
```
4. Create settings.json from template and fill it
```
cp settings.json.example settings.json
```
5. Create restart.sh and add some server restart logic
6. Run main.py
```
python main.py
```