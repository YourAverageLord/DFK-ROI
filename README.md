# DFK-ROI
Get return on investment info for your DFK heroes!
<br>

## Setup
```bash
cd DFK-ROI/

# Create a virtual env
python3 -m venv .venv

# Activate your virtual env 
source ./.venv/bin/activate

# Upgrade `pip`
python3 -m pip install --upgrade pip

# install the dependencies to your virtual env
python3 -m install -r requirements.txt
```
<br>

---
## Usage
```bash
python3 DFK-roi.py -h
```
```
usage: python3 DFK-roi.py [-h] -a ADDRESS [--rentals] [--quest-rewards]

DFK ROI!

optional arguments:
  -h, --help            show this help message and exit
  -a ADDRESS, --address ADDRESS
                        Specify the 0x address you want to get an ROI report
                        for.
  --rentals             Query tavern rental profits
  --quest-rewards       Query quest reward profits
```
<br>

### Get lifetime rental info for your gen0 heroes
```bash
python3 DFK-roi.py --rentals -a "0xaddresshere"
```
![image](https://user-images.githubusercontent.com/99366718/175788963-b1ed9fb2-6371-4412-a19d-22b54de27524.png)
<br>

---
### Get lifetime quest rewards for all heroes you've ever had in your wallet.
```bash
python3 DFK-roi.py --quest-rewards -a "0xaddresshere"
```

This will save a file to `output/quest_rewards.json` that contains a list of all your heroes and all the quest rewards they've ever recieved while in your specified wallet.
![image](https://user-images.githubusercontent.com/99366718/175789007-ebd4fd59-c88f-482e-a55e-8d2171397b32.png)
