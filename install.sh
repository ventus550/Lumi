pyinstaller ./lumi.py --upx-dir=../upx391 -y --onefile
sudo mv ./dist/lumi /usr/bin/
rm -rf ./build ./dist ./lumi.spec