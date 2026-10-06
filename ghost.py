#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ghost 拼词游戏：轮流给词片段加字母，拼出完整单词者输；可质疑 bluff。"""

from __future__ import annotations

import argparse
import functools
import random
import sys

MIN_LEN = 4  # 拼出至少这么长的单词才算输

# 内置英文词表（均为小写常见词，长度 >= 4，无专有名词）
WORDS = """about above actor after again agree allow alone along aloud alter angel anger
angle apple apply arena argue armed arrive aside asset avoid awake bacon badge badly
baker basic beach beard beast begin belly bench berry birth black blade blame blank
blast blend bless blind block blood board bonus booth bound brain brand brave bread
break brick bride brief bring broad broke brown brush build bunch buyer cabin cable
camel candy carry catch cause chain chair charm chart chase cheap check cheese chest
chicken chief child choir choose civil claim class clean clear clerk clever click
climb clock close cloth cloud coach coast color could count court cover crack craft
crash crazy cream crime cross crowd crown daily dance death delay depth diary dirty
doubt dozen draft drain drama dream dress drink drive eager early earth eight elbow
elder elect empty enemy enjoy enter entry equal error essay event every exact exist
extra faint fairy faith fancy fault favor feast fence fever fiber field fifth fifty
fight final first flame flash fleet flesh float flood floor flour fluid focus force
forth forty forum found frame fresh front frost fruit funny giant given glass globe
grace grade grain grand grant grass great green greet grief group guard guess guest
guide habit happy heart heavy hello honey honor horse hotel house human hurry ideal
image imply index inner input issue ivory joint judge juice knife knock known label
labor large later laugh layer learn least leave legal lemon level light limit liver
local logic loose lover lower lucky lunch magic major maker march match maybe mayor
meant medal media merry metal meter might minor minus model money month moral motor
mount mouse mouth movie music nasty never night noble noise north novel nurse occur
ocean offer often older olive onion opera order other ought outer owner paint panel
paper party peace penny phase phone photo piano piece pilot pitch place plain plane
plant plate point pound power press price pride prime print prize proof proud prove
queen quick quiet quite radio raise range rapid ratio reach ready realm rebel refer
relax reply rider right river roast robot rocky roman rough round route royal rural
salad scale scene score sense serve seven shade shake shall shape share sharp sheep
sheet shelf shell shift shine shirt shock shore short shout shown sight silly since
sixth sixty skill skirt sleep slice slide slope small smart smell smile smoke snake
solar solid solve sorry sound south space spare speak speed spell spend spice split
spoke sport staff stage stair stand start state steam steel steep stick still stock
stone stood store storm story strip style sugar sunny super sweet table taken taste
teach teeth thank their theme there thick thing think third those three threw throw
thumb tiger tight tired title today token tooth total touch tough tower town trace
track trade trail train treat trend trial tribe trick truck truly trust truth twice
under union unite until upper upset urban usual valid value video visit vital voice
waste watch water weave wheel where which while white whole whose woman women world
worry worth would wound write wrong wrote yield young youth""".split()


class IllegalMove(ValueError):
    """非法走法。"""


class _TrieNode:
    __slots__ = ("children", "is_word")

    def __init__(self):
        self.children = {}
        self.is_word = False


class Ghost:
    """Ghost 引擎：两名玩家轮流加字母。"""

    def __init__(self, words=None, min_len=MIN_LEN, rng=None):
        self.words = sorted({w for w in (words or WORDS)
                             if w.isalpha() and len(w) >= min_len})
        self.wordset = set(self.words)
        self.min_len = min_len
        self.rng = rng or random.Random()
        self.fragment = ""
        self.turn = 0
        self.over = False
        self.loser = None
        self.reason = ""
        # 前缀树，供最优 AI 做 DP
        self._trie = _TrieNode()
        for w in self.words:
            node = self._trie
            for ch in w:
                node = node.children.setdefault(ch, _TrieNode())
            node.is_word = True

    # ---- 查询 ----
    def is_word(self, frag):
        return len(frag) >= self.min_len and frag in self.wordset

    def is_prefix(self, frag):
        return any(w.startswith(frag) for w in self.words)

    def continuations(self, frag):
        return [w for w in self.words if w.startswith(frag)]

    # ---- 走法 ----
    def add_letter(self, ch):
        """当前玩家加一个字母；拼出单词则当场判负。"""
        if self.over:
            raise IllegalMove("对局已结束")
        if not (isinstance(ch, str) and len(ch) == 1 and ch.isalpha()):
            raise IllegalMove("必须输入单个英文字母")
        ch = ch.lower()
        new = self.fragment + ch
        if self.is_word(new):
            self.fragment = new
            self.over = True
            self.loser = self.turn
            self.reason = f"玩家{self.turn} 拼出了单词 {new!r}"
        else:
            self.fragment = new
            self.turn = 1 - self.turn
        return new

    def challenge(self):
        """当前玩家质疑上家：上家须证明片段能拼成单词。"""
        if self.over:
            raise IllegalMove("对局已结束")
        if not self.fragment:
            raise IllegalMove("空片段不能质疑")
        challenger = self.turn
        previous = 1 - self.turn
        if self.is_prefix(self.fragment):
            # 上家能自证：质疑者输
            self.over = True
            self.loser = challenger
            self.reason = (f"玩家{previous} 自证片段 {self.fragment!r} 可拼词，"
                           f"玩家{challenger} 质疑失败")
        else:
            # bluff 被抓：上家输
            self.over = True
            self.loser = previous
            self.reason = (f"片段 {self.fragment!r} 不是任何单词前缀，"
                           f"玩家{previous} 虚张声势被抓")
        return self.loser

    # ---- AI（DP 最优） ----
    def _walk(self, frag):
        node = self._trie
        for ch in frag:
            node = node.children.get(ch)
            if node is None:
                return None
        return node

    def _safe_letters(self, frag):
        """不拼出单词且仍是前缀的字母。"""
        node = self._walk(frag)
        if node is None:
            return []
        out = []
        for ch, child in node.children.items():
            if len(frag) + 1 >= self.min_len and child.is_word:
                continue  # 加了就输，不是安全走法
            out.append(ch)
        return out

    @functools.lru_cache(maxsize=None)
    def _losing(self, frag):
        """DP：轮到走棋的一方在 frag 是否必输（双方最优、无 bluff）。"""
        safe = self._safe_letters(frag)
        if not safe:
            return True  # 无安全走法，只能拼词认输
        return all(not self._losing(frag + ch) for ch in safe)

    def ai_should_challenge(self):
        return bool(self.fragment) and not self.is_prefix(self.fragment)

    def ai_letter(self):
        """最优走法：有必胜走法则走之，否则随便走安全字母拖延。"""
        if self.ai_should_challenge():
            raise IllegalMove("AI 应质疑而非加字母")
        safe = self._safe_letters(self.fragment)
        if not safe:
            raise IllegalMove("无安全字母，AI 只能认输")
        winning = [ch for ch in safe if self._losing(self.fragment + ch)]
        if winning:
            return self.rng.choice(winning)
        return self.rng.choice(safe)

    def ai_move(self):
        if self.ai_should_challenge():
            return ("challenge", self.challenge())
        if not self._safe_letters(self.fragment):
            # 无安全走法：被迫拼出单词认输
            node = self._walk(self.fragment)
            ch = next(iter(node.children))
            self.add_letter(ch)  # 触发判负
            return ("letter", ch)
        ch = self.ai_letter()
        self.add_letter(ch)
        return ("letter", ch)

    def winner(self):
        return None if self.loser is None else 1 - self.loser


def play_auto_game(seed=None, words=None):
    rng = random.Random(seed)
    g = Ghost(words=words, rng=rng)
    moves = 0
    while not g.over:
        g.ai_move()
        moves += 1
        if moves > 1000:  # 熔断，理论上到不了
            g.over = True
            g.loser = g.turn
            g.reason = "步数熔断"
    return g


def run_auto(games, seed):
    rng = random.Random(seed)
    wins = [0, 0]
    for i in range(games):
        g = play_auto_game(seed=rng.randrange(1 << 30))
        wins[g.winner()] += 1
        print(f"第 {i + 1}/{games} 局：玩家{g.winner()} 胜（{g.reason}）")
    print(f"总计：玩家0 胜 {wins[0]}，玩家1 胜 {wins[1]}")


def play_interactive(human_first=True, seed=None):
    rng = random.Random(seed)
    g = Ghost(rng=rng)
    human = 0 if human_first else 1
    print("=== Ghost 拼词游戏 ===")
    print("规则：轮流加一个字母，拼出完整单词（≥4字母）者输。")
    print("输入 ! 可质疑上家（上家须证明片段能拼成单词）。")
    print(f"你是玩家{human}，{'先手' if human_first else '后手'}。")
    while not g.over:
        print(f"\n当前片段：{g.fragment!r}  轮到玩家{g.turn}")
        if g.turn == human:
            s = input("加字母（或 ! 质疑）：").strip().lower()
            try:
                if s == "!":
                    loser = g.challenge()
                    print(f"质疑结果：玩家{loser} 输。{g.reason}")
                else:
                    g.add_letter(s)
                    if g.over:
                        print(f"你拼出了单词 {g.fragment!r}，你输了！")
            except IllegalMove as e:
                print(f"非法：{e}")
        else:
            kind, val = g.ai_move()
            if kind == "challenge":
                print(f"AI 质疑！{g.reason}")
            else:
                print(f"AI 加了字母 {val!r}，片段变为 {g.fragment!r}")
                if g.over:
                    print(f"AI 拼出了单词 {g.fragment!r}，AI 输了，你赢了！")
    print(f"\n对局结束：玩家{g.winner()} 获胜。")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Ghost 拼词游戏")
    ap.add_argument("--auto", action="store_true", help="AI 对 AI 自动演示")
    ap.add_argument("--games", type=int, default=10, help="自动演示局数")
    ap.add_argument("--seed", type=int, default=42, help="随机种子")
    ap.add_argument("--second", action="store_true", help="交互模式中人类后手")
    args = ap.parse_args(argv)
    if args.auto:
        run_auto(args.games, args.seed)
    else:
        if not sys.stdin.isatty():
            print("交互模式需要终端；请用 --auto 自动演示。", file=sys.stderr)
            return 2
        play_interactive(human_first=not args.second, seed=args.seed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
