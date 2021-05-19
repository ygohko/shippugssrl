=============
SHIPPU GSS NN
=============
SHIPPU GSS is a experimental implementation of neural network based automated
playing of time attack shooter game.

How to execute
==============
Before the execution install Python, Pygame and NumPy and then execute gss.py.

gss.py outputs pickle files that includes gene information when altering
generation. To continue execution, give this file as command line option.

Command line
------------
Command line synopsis is below::

    $ python3 gss.py [OPTION] [GENE FILE]

Options
-------
* -n ... No wait
* -s ... Silent

How to control
==============
* Esc key ... Exit game / return to home

License
=======
This software is distributed under the MIT License.

History
=======
* Version 0.0.0 ... (not released yet)

=============
SHIPPU GSS NN
=============
SHIPPU GSSはタイムアタックシューティングをベースにしたニューラルネットワークに
よる自動プレイの実験です。

実行方法
========
Python、Pygame、NumPyをインストール後、gss.pyを実行してください。

実行中は世代交代時に遺伝子情報が記録されたpickleファイルを出力します。起動時に
引数でこのファイルを指定することにより途中から継続して実行することができます。

コマンドライン
--------------
コマンドラインは以下の通りです::

    $ python3 gss.py [オプション] [遺伝子情報ファイル]

オプション
----------
* -n ... ノーウエイト
* -s ... サイレント

操作方法
========
* Escキー ... ゲーム終了 / タイトル画面に戻る

ライセンス
==========
MITライセンスで配布します。

歴史
====
* バージョン0.0.0 ... (まだ)
