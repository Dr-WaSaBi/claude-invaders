#!/usr/bin/env python3
"""Claude Invaders — protect humanity from the descending Claude horde."""

import pygame
import random
import math
import sys
import json
import numpy as np
from pathlib import Path

pygame.mixer.pre_init(44100, -16, 2, 512)
pygame.init()

# ── screen ─────────────────────────────────────────────────────────────────────
W, H = 900, 700
screen = pygame.display.set_mode((W, H))
pygame.display.set_caption("Claude Invaders")
clock = pygame.time.Clock()
FPS = 60

# ── palette ────────────────────────────────────────────────────────────────────
BLACK     = (  0,   0,   0)
SKY       = (  8,   8,  28)
WHITE     = (255, 255, 255)
CLAUDE_O  = (210, 140,  65)   # Claude orange
CLAUDE_D  = (130,  78,  18)   # dark accent
CLAUDE_H  = (240, 175, 105)   # highlight
MX_GRN    = (  0, 230,  80)   # matrix green
MX_DIM    = (  0, 100,  30)
MX_BRIGHT = (180, 255, 180)
RED       = (220,  40,  40)
YELLOW    = (255, 220,   0)
SKIN      = (255, 205, 155)
SHIRT     = ( 55, 120, 190)
PANTS     = ( 30,  50, 100)
HAIR      = ( 60,  35,  10)
BLDG_BASE = ( 60,  75,  85)
BLDG_HIT1 = ( 50,  62,  72)
BLDG_HIT2 = ( 38,  48,  58)
STAR_C    = (200, 210, 255)
BULLET_C  = (255, 255, 100)
GROUND    = ( 30,  35,  50)

MATRIX_CHARS = "01アイウエオ$%#@&イ01カキ"

# ── font ───────────────────────────────────────────────────────────────────────
font_big   = pygame.font.SysFont("monospace", 48, bold=True)
font_med   = pygame.font.SysFont("monospace", 26, bold=True)
font_small = pygame.font.SysFont("monospace", 16)

# ── sound engine ───────────────────────────────────────────────────────────────
class SoundEngine:
    SR = 44100

    def __init__(self):
        self._march_sounds = [self._tone(f, 0.09, 'square', 0.22)
                              for f in (160, 130, 110, 85)]
        self._march_idx = 0
        self.shoot      = self._sweep(580, 140, 0.09, 'square', 0.18)
        self.kill       = self._kill_sound()
        self.player_hit = self._player_hit_sound()
        self.bldg_hit   = self._tone(110, 0.07, 'square', 0.14)
        self.fanfare    = self._fanfare_sound()

    # ── synthesis helpers ──────────────────────────────────────────────────────
    def _t(self, duration):
        return np.linspace(0, duration, int(self.SR * duration), endpoint=False)

    def _bake(self, arr, vol=0.3):
        arr = np.clip(arr * vol, -1.0, 1.0)
        s16 = (arr * 32767).astype(np.int16)
        return pygame.sndarray.make_sound(np.ascontiguousarray(np.column_stack([s16, s16])))

    def _tone(self, freq, dur, wave='square', vol=0.3):
        t = self._t(dur)
        s = np.sign(np.sin(2 * np.pi * freq * t)) if wave == 'square' \
            else np.sin(2 * np.pi * freq * t)
        fade = max(1, int(len(t) * 0.2))
        s[-fade:] *= np.linspace(1, 0, fade)
        return self._bake(s, vol)

    def _sweep(self, f0, f1, dur, wave='square', vol=0.2):
        t = self._t(dur)
        phase = np.cumsum(np.linspace(f0, f1, len(t)) / self.SR * 2 * np.pi)
        s = np.sign(np.sin(phase)) if wave == 'square' else np.sin(phase)
        fade = max(1, int(len(t) * 0.15))
        s[-fade:] *= np.linspace(1, 0, fade)
        return self._bake(s, vol)

    def _kill_sound(self):
        t = self._t(0.28)
        noise = np.random.default_rng(0).uniform(-1, 1, len(t))
        env   = np.exp(-t * 18)
        phase = np.cumsum(np.linspace(420, 45, len(t)) / self.SR * 2 * np.pi)
        tone  = np.sign(np.sin(phase)) * 0.5
        return self._bake((noise * 0.5 + tone * 0.5) * env, 0.38)

    def _player_hit_sound(self):
        t = self._t(0.75)
        noise = np.random.default_rng(1).uniform(-1, 1, len(t))
        env   = np.exp(-t * 5.5)
        phase = np.cumsum(np.linspace(240, 28, len(t)) / self.SR * 2 * np.pi)
        tone  = np.sin(phase) * 0.6
        return self._bake((noise * 0.4 + tone * 0.6) * env, 0.52)

    def _fanfare_sound(self):
        notes, dur = [262, 330, 392, 523], 0.11
        parts = []
        for freq in notes:
            t = self._t(dur)
            s = np.sign(np.sin(2 * np.pi * freq * t))
            fade = max(1, int(len(t) * 0.2))
            s[-fade:] *= np.linspace(1, 0, fade)
            parts.append(s)
        return self._bake(np.concatenate(parts), 0.22)

    # ── play helpers ───────────────────────────────────────────────────────────
    def march(self):
        self._march_sounds[self._march_idx % 4].play()
        self._march_idx += 1

    def play(self, name: str):
        getattr(self, name).play()


sfx = SoundEngine()

# ── high scores ────────────────────────────────────────────────────────────────
class HighScores:
    MAX  = 10
    FILE = Path(__file__).parent / "highscores.json"

    def __init__(self):
        self.scores: list[dict] = []
        self._load()

    def _load(self):
        try:
            data = json.loads(self.FILE.read_text())
            self.scores = sorted(data, key=lambda x: x["score"], reverse=True)[:self.MAX]
        except Exception:
            self.scores = []

    def _save(self):
        self.FILE.write_text(json.dumps(self.scores, indent=2))

    def is_qualifying(self, score: int) -> bool:
        if score <= 0:
            return False
        if len(self.scores) < self.MAX:
            return True
        return score > self.scores[-1]["score"]

    def rank(self, score: int) -> int:
        for i, entry in enumerate(self.scores):
            if score >= entry["score"]:
                return i + 1
        return len(self.scores) + 1

    def add(self, name: str, score: int):
        self.scores.append({"name": name.upper()[:3].ljust(3), "score": score})
        self.scores.sort(key=lambda x: x["score"], reverse=True)
        self.scores = self.scores[:self.MAX]
        self._save()

    def top_score(self) -> int:
        return self.scores[0]["score"] if self.scores else 0


hs = HighScores()

# ── sprite helpers ─────────────────────────────────────────────────────────────
def make_claude_surf(size: int, frame: int = 0) -> pygame.Surface:
    """Render a single Claude-logo-style alien to a surface."""
    sw = size
    sh = size + size // 4          # a bit taller for legs
    surf = pygame.Surface((sw, sh), pygame.SRCALPHA)

    # body
    body = pygame.Rect(0, 0, sw, size)
    pygame.draw.rect(surf, CLAUDE_O, body, border_radius=size // 5)
    pygame.draw.rect(surf, CLAUDE_D, body, width=2, border_radius=size // 5)
    # inner highlight strip
    hi = pygame.Rect(size // 6, size // 8, size * 2 // 3, size // 5)
    pygame.draw.rect(surf, CLAUDE_H, hi, border_radius=size // 8)

    # eyes
    ey = size // 3
    er = max(3, size // 9)
    for ex in (size // 4, 3 * size // 4):
        pygame.draw.circle(surf, CLAUDE_D, (ex, ey), er)
        pygame.draw.circle(surf, (255, 165, 50), (ex, ey), max(1, er - 2))

    # mouth — angular C-like mark
    mx, my = size // 2, size * 2 // 3
    mw, mh = size * 2 // 5, size // 5
    pygame.draw.arc(surf, CLAUDE_D,
                    (mx - mw // 2, my - mh // 2, mw, mh),
                    math.pi * 0.1, math.pi * 0.9, 2)

    # legs (2 frames)
    lc = CLAUDE_D
    offsets = [(-size // 4, size // 8), (0, 0), (size // 4, size // 8)] if frame == 0 else \
              [(-size // 4, 0), (0, size // 8), (size // 4, 0)]
    for i, (ox, oy) in enumerate(offsets):
        bx = size // 4 + i * (size // 4)
        pygame.draw.line(surf, lc, (bx, size), (bx + ox, size + size // 6 + oy), 3)

    return surf


def make_human_surf(size: int = 28) -> pygame.Surface:
    """Simple pixel-human sprite."""
    surf = pygame.Surface((size, size * 2), pygame.SRCALPHA)
    s = size
    # head
    pygame.draw.circle(surf, SKIN, (s // 2, s // 4), s // 4)
    # hair
    pygame.draw.arc(surf, HAIR,
                    (s // 2 - s // 4, 0, s // 2, s // 2), 0, math.pi, 4)
    # body
    pygame.draw.rect(surf, SHIRT, (s // 4, s // 2, s // 2, s // 2))
    # arms
    pygame.draw.line(surf, SKIN, (s // 4, s // 2), (s // 8, s * 3 // 4), 3)
    pygame.draw.line(surf, SKIN, (3 * s // 4, s // 2), (7 * s // 8, s * 3 // 4), 3)
    # legs
    pygame.draw.rect(surf, PANTS, (s // 4, s, s // 5, s // 2))
    pygame.draw.rect(surf, PANTS, (s // 2, s, s // 5, s // 2))
    # gun (held to side)
    pygame.draw.rect(surf, (80, 80, 80), (3 * s // 4, s // 2 + 4, s // 4, 4))
    return surf


# ── building blocks ─────────────────────────────────────────────────────────────
BLOCK = 8          # pixels per building block
BLD_W = 11         # blocks wide
BLD_H = 6          # blocks tall

# shape mask (True = solid block), rounded bunker silhouette
def bunker_mask():
    mask = [[True] * BLD_W for _ in range(BLD_H)]
    # carve notch at bottom centre (doorway)
    for r in range(BLD_H - 2, BLD_H):
        for c in range(BLD_W // 2 - 1, BLD_W // 2 + 2):
            mask[r][c] = False
    # round top corners
    for c in range(2):
        mask[0][c] = False
        mask[0][BLD_W - 1 - c] = False
    return mask


# ── game objects ───────────────────────────────────────────────────────────────
class Building:
    def __init__(self, cx: int, y: int):
        self.mask = bunker_mask()
        self.x = cx - BLD_W * BLOCK // 2
        self.y = y

    def draw(self, surf):
        for r, row in enumerate(self.mask):
            for c, alive in enumerate(row):
                if not alive:
                    continue
                rx = self.x + c * BLOCK
                ry = self.y + r * BLOCK
                # color based on row damage heuristic (just use base color)
                pygame.draw.rect(surf, BLDG_BASE, (rx, ry, BLOCK - 1, BLOCK - 1))
                pygame.draw.rect(surf, BLDG_HIT1, (rx, ry, BLOCK - 1, 2))

    def hit_test(self, bx, by, w=4, h=8):
        """Return True if rect (bx,by,w,h) collides with any solid block; destroy hit blocks."""
        hit = False
        for r in range(BLD_H):
            for c in range(BLD_W):
                if not self.mask[r][c]:
                    continue
                rx = self.x + c * BLOCK
                ry = self.y + r * BLOCK
                if bx < rx + BLOCK and bx + w > rx and by < ry + BLOCK and by + h > ry:
                    self.mask[r][c] = False
                    # also destroy adjacent block for chunky damage
                    nr, nc = r + random.choice([-1, 0, 1]), c + random.choice([-1, 0, 1])
                    if 0 <= nr < BLD_H and 0 <= nc < BLD_W:
                        self.mask[nr][nc] = False
                    hit = True
        return hit

    def column_hit(self, cx, cy):
        """Destroy blocks in a 2-block column at pixel x=cx from row containing cy down."""
        for c in range(BLD_W):
            if self.x + c * BLOCK <= cx < self.x + (c + 1) * BLOCK:
                for r in range(BLD_H):
                    ry = self.y + r * BLOCK
                    if ry >= cy:
                        if self.mask[r][c]:
                            self.mask[r][c] = False
                            return True
        return False


class MatrixBomb:
    """A column of falling green matrix characters."""
    SPEED = 180       # px/s
    TRAIL = 10        # number of chars in trail

    def __init__(self, x, y):
        self.x = x
        self.y = float(y)
        self.chars = [random.choice(MATRIX_CHARS) for _ in range(self.TRAIL)]
        self.tick = 0.0
        self.dead = False

    def update(self, dt):
        self.y += self.SPEED * dt
        self.tick += dt
        if self.tick > 0.07:
            self.tick = 0.0
            self.chars = [random.choice(MATRIX_CHARS)] + self.chars[:-1]

    def draw(self, surf):
        for i, ch in enumerate(self.chars):
            brightness = 1.0 - i / self.TRAIL
            if i == 0:
                color = MX_BRIGHT
            elif i < 2:
                color = MX_GRN
            else:
                r = int(MX_DIM[0] + (MX_GRN[0] - MX_DIM[0]) * brightness)
                g = int(MX_DIM[1] + (MX_GRN[1] - MX_DIM[1]) * brightness)
                b = int(MX_DIM[2] + (MX_GRN[2] - MX_DIM[2]) * brightness)
                color = (r, g, b)
            cy = int(self.y) - i * 14
            txt = font_small.render(ch, True, color)
            surf.blit(txt, (self.x - 6, cy))

    @property
    def tip_rect(self):
        return pygame.Rect(self.x - 4, int(self.y) - 4, 8, 8)


class Bullet:
    SPEED = 550

    def __init__(self, x, y):
        self.x = float(x)
        self.y = float(y)
        self.dead = False

    def update(self, dt):
        self.y -= self.SPEED * dt
        if self.y < -10:
            self.dead = True

    def draw(self, surf):
        pygame.draw.rect(surf, BULLET_C, (int(self.x) - 2, int(self.y) - 8, 4, 12))
        pygame.draw.rect(surf, WHITE, (int(self.x) - 1, int(self.y) - 8, 2, 5))


class Particle:
    def __init__(self, x, y, color):
        self.x = float(x)
        self.y = float(y)
        angle = random.uniform(0, math.tau)
        speed = random.uniform(60, 220)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.life = random.uniform(0.3, 0.8)
        self.max_life = self.life
        self.color = color
        self.r = random.randint(2, 5)

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vy += 200 * dt
        self.life -= dt

    def draw(self, surf):
        alpha = self.life / self.max_life
        r, g, b = self.color
        col = (int(r * alpha), int(g * alpha), int(b * alpha))
        pygame.draw.circle(surf, col, (int(self.x), int(self.y)), self.r)


class Player:
    SPEED = 320
    SHOT_COOLDOWN = 0.35

    def __init__(self):
        self.surf = make_human_surf(28)
        self.w = self.surf.get_width()
        self.h = self.surf.get_height()
        self.x = float(W // 2)
        self.y = float(H - 80)
        self.cooldown = 0.0
        self.lives = 3
        self.invincible = 0.0   # seconds of invincibility after hit
        self.dead = False

    def update(self, dt, keys):
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            self.x = max(self.w // 2, self.x - self.SPEED * dt)
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            self.x = min(W - self.w // 2, self.x + self.SPEED * dt)
        self.cooldown = max(0.0, self.cooldown - dt)
        self.invincible = max(0.0, self.invincible - dt)

    def shoot(self):
        if self.cooldown <= 0:
            self.cooldown = self.SHOT_COOLDOWN
            return Bullet(self.x, self.y - self.h // 2)
        return None

    def draw(self, surf):
        if self.invincible > 0 and int(self.invincible * 10) % 2:
            return   # flash while invincible
        surf.blit(self.surf, (int(self.x) - self.w // 2, int(self.y) - self.h // 2))

    @property
    def rect(self):
        return pygame.Rect(int(self.x) - self.w // 2, int(self.y) - self.h // 2,
                           self.w, self.h)


class ClaudeAlien:
    SIZE = 36

    def __init__(self, col, row, x, y):
        self.col = col
        self.row = row
        self.x = float(x)
        self.y = float(y)
        self.frame = 0
        self.anim_tick = 0.0
        self.alive = True
        self.surfs = [make_claude_surf(self.SIZE, f) for f in (0, 1)]

    def draw(self, surf):
        if not self.alive:
            return
        s = self.surfs[self.frame]
        surf.blit(s, (int(self.x) - self.SIZE // 2, int(self.y) - self.SIZE // 2))

    def tick_anim(self, dt):
        self.anim_tick += dt
        if self.anim_tick > 0.4:
            self.anim_tick = 0.0
            self.frame ^= 1

    @property
    def rect(self):
        s = self.SIZE
        return pygame.Rect(int(self.x) - s // 2, int(self.y) - s // 2, s, s)


# ── formation ──────────────────────────────────────────────────────────────────
COLS = 11
ROWS = 4
HGAP = 62
VGAP = 54
START_X = W // 2 - (COLS - 1) * HGAP // 2
START_Y = 90


class Formation:
    STEP_DOWN = 22
    DROP_INTERVAL = 0.6    # seconds between drops (scales with kills)

    def __init__(self):
        self.aliens: list[ClaudeAlien] = []
        self._build()
        self.dir = 1           # +1 right, -1 left
        self.move_timer = 0.0
        self.move_interval = 0.8
        self.drop_timer = 0.0
        self.drop_interval = self.DROP_INTERVAL
        self.step_px = 14      # horizontal step per move
        self.stepped = False   # set True each time the formation moves

    def _build(self):
        for row in range(ROWS):
            for col in range(COLS):
                x = START_X + col * HGAP
                y = START_Y + row * VGAP
                self.aliens.append(ClaudeAlien(col, row, x, y))

    @property
    def alive_aliens(self):
        return [a for a in self.aliens if a.alive]

    def update(self, dt):
        alive = self.alive_aliens
        if not alive:
            return

        # speed up as fewer Claudes remain
        total = COLS * ROWS
        ratio = len(alive) / total
        self.move_interval = max(0.08, 0.8 * ratio)

        for a in alive:
            a.tick_anim(dt)

        self.stepped = False
        self.move_timer += dt
        if self.move_timer >= self.move_interval:
            self.move_timer = 0.0
            self._step()
            self.stepped = True

        self.drop_timer += dt
        if self.drop_timer >= self.drop_interval:
            self.drop_timer = 0.0

    def _step(self):
        alive = self.alive_aliens
        if not alive:
            return
        xs = [a.x for a in alive]
        left, right = min(xs), max(xs)
        margin = ClaudeAlien.SIZE // 2 + 8

        if self.dir == 1 and right + self.step_px >= W - margin:
            self._drop()
            self.dir = -1
        elif self.dir == -1 and left - self.step_px <= margin:
            self._drop()
            self.dir = 1
        else:
            for a in alive:
                a.x += self.dir * self.step_px

    def _drop(self):
        for a in self.alive_aliens:
            a.y += self.STEP_DOWN

    def try_drop_bomb(self) -> "MatrixBomb | None":
        """Return a new bomb from a random front-row alien."""
        alive = self.alive_aliens
        if not alive:
            return None
        # pick from bottom-most alien in a random column
        cols: dict[int, ClaudeAlien] = {}
        for a in alive:
            if a.col not in cols or a.y > cols[a.col].y:
                cols[a.col] = a
        shooter = random.choice(list(cols.values()))
        return MatrixBomb(int(shooter.x), int(shooter.y) + ClaudeAlien.SIZE // 2)

    def lowest_y(self):
        alive = self.alive_aliens
        return max(a.y for a in alive) if alive else 0


# ── stars ──────────────────────────────────────────────────────────────────────
STARS = [(random.randint(0, W), random.randint(0, H - 120),
          random.randint(1, 3)) for _ in range(120)]


def draw_stars(surf):
    for sx, sy, br in STARS:
        c = (min(255, STAR_C[0] * br // 3),
             min(255, STAR_C[1] * br // 3),
             min(255, STAR_C[2] * br // 3))
        surf.set_at((sx, sy), c)


# ── HUD ────────────────────────────────────────────────────────────────────────
def draw_hud(surf, score, lives, level, hi):
    pygame.draw.rect(surf, (15, 15, 40), (0, 0, W, 40))
    surf.blit(font_med.render(f"SCORE {score:06d}", True, WHITE), (10, 7))
    surf.blit(font_med.render(f"HI {hi:06d}", True, YELLOW), (W // 2 - 60, 7))
    surf.blit(font_med.render(f"LEVEL {level}", True, MX_GRN), (W - 160, 7))
    # lives as tiny claude icons
    for i in range(lives):
        tiny = make_claude_surf(18, 0)
        surf.blit(tiny, (10 + i * 24, 46))


# ── screens ────────────────────────────────────────────────────────────────────
def draw_scores_table(surf, cx: int, y: int, count: int = 10, highlight: int = -1):
    """Draw the high scores table centred on cx, starting at y. highlight is 1-based rank."""
    hdr = font_small.render("  #   NAME    SCORE", True, CLAUDE_O)
    surf.blit(hdr, (cx - hdr.get_width() // 2, y))
    pygame.draw.line(surf, CLAUDE_D, (cx - 120, y + 22), (cx + 120, y + 22), 1)
    y += 28
    for i, entry in enumerate(hs.scores[:count]):
        rank = i + 1
        line = f" {rank:>2}.  {entry['name']}   {entry['score']:>06d}"
        col  = YELLOW if rank == highlight else (WHITE if rank <= 3 else GRAY)
        row  = font_small.render(line, True, col)
        surf.blit(row, (cx - row.get_width() // 2, y + i * 22))
    if not hs.scores:
        empty = font_small.render("— no scores yet —", True, GRAY)
        surf.blit(empty, (cx - empty.get_width() // 2, y))


def enter_initials_screen(score: int, rank: int) -> str:
    """Classic 3-letter arcade initials entry. Returns the chosen string."""
    letters = ['A', 'A', 'A']
    pos     = 0
    t       = 0.0

    while True:
        dt = clock.tick(FPS) / 1000
        t += dt

        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if e.type == pygame.KEYDOWN:
                if e.key in (pygame.K_UP, pygame.K_w):
                    letters[pos] = chr((ord(letters[pos]) - ord('A') - 1) % 26 + ord('A'))
                elif e.key in (pygame.K_DOWN, pygame.K_s):
                    letters[pos] = chr((ord(letters[pos]) - ord('A') + 1) % 26 + ord('A'))
                elif e.key in (pygame.K_RIGHT, pygame.K_SPACE):
                    if pos < 2:
                        pos += 1
                    else:
                        return ''.join(letters)
                elif e.key in (pygame.K_LEFT, pygame.K_BACKSPACE):
                    pos = max(0, pos - 1)
                elif e.key == pygame.K_RETURN:
                    return ''.join(letters)
                elif e.key == pygame.K_ESCAPE:
                    return 'AAA'
                elif pygame.K_a <= e.key <= pygame.K_z:
                    letters[pos] = chr(e.key - pygame.K_a + ord('A'))
                    if pos < 2:
                        pos += 1

        screen.fill(SKY)
        draw_stars(screen)

        t1 = font_big.render("NEW HIGH SCORE!", True, YELLOW)
        screen.blit(t1, (W // 2 - t1.get_width() // 2, 80))

        t2 = font_med.render(f"{score:06d}   RANK #{rank}", True, WHITE)
        screen.blit(t2, (W // 2 - t2.get_width() // 2, 150))

        hint = font_small.render("↑ ↓  change letter      → / SPACE  next      ENTER  confirm", True, GRAY)
        screen.blit(hint, (W // 2 - hint.get_width() // 2, 210))

        # letter slots
        slot_w, gap = 80, 18
        total = 3 * slot_w + 2 * gap
        sx = W // 2 - total // 2
        for i, ch in enumerate(letters):
            blink  = (pos == i and int(t * 3) % 2 == 0)
            active = (pos == i)
            col    = YELLOW if active else WHITE
            rect   = pygame.Rect(sx + i * (slot_w + gap), 250, slot_w, 100)
            pygame.draw.rect(screen, (35, 35, 70) if active else (20, 20, 45), rect, border_radius=10)
            pygame.draw.rect(screen, col, rect, width=2, border_radius=10)
            if not blink:
                cs = font_big.render(ch, True, col)
                screen.blit(cs, (rect.centerx - cs.get_width() // 2,
                                  rect.centery - cs.get_height() // 2))

        draw_scores_table(screen, W // 2, 375, count=5, highlight=rank)

        pygame.display.flip()


def title_screen():
    alien_surf = make_claude_surf(56, 0)
    t = 0.0
    while True:
        dt = clock.tick(FPS) / 1000
        t += dt
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if e.type == pygame.KEYDOWN:
                if e.key in (pygame.K_RETURN, pygame.K_SPACE):
                    return
                if e.key == pygame.K_ESCAPE:
                    pygame.quit(); sys.exit()

        screen.fill(SKY)
        draw_stars(screen)

        # title
        title = font_big.render("CLAUDE  INVADERS", True, CLAUDE_O)
        screen.blit(title, (W // 2 - title.get_width() // 2, 120))

        # animated alien sample
        bob = int(math.sin(t * 2) * 6)
        screen.blit(alien_surf, (W // 2 - 28, 200 + bob))

        sub = font_med.render("They're here. They're orange. They're recursive.", True, MX_GRN)
        screen.blit(sub, (W // 2 - sub.get_width() // 2, 290))

        inst = [
            "← → / A D   Move",
            "SPACE         Fire",
            "ESC           Quit",
        ]
        for i, line in enumerate(inst):
            s = font_small.render(line, True, WHITE)
            screen.blit(s, (W // 2 - s.get_width() // 2, 360 + i * 26))

        blink = font_med.render("PRESS ENTER TO PLAY", True,
                                 YELLOW if int(t * 2) % 2 == 0 else (180, 160, 0))
        screen.blit(blink, (W // 2 - blink.get_width() // 2, 480))

        draw_scores_table(screen, W // 2, 530, count=5)

        pygame.display.flip()


def game_over_screen(score, hi, won=False):
    t = 0.0
    while True:
        dt = clock.tick(FPS) / 1000
        t += dt
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if e.type == pygame.KEYDOWN:
                if e.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_r):
                    return
                if e.key == pygame.K_ESCAPE:
                    pygame.quit(); sys.exit()

        screen.fill(SKY)
        draw_stars(screen)

        if won:
            msg = font_big.render("YOU WIN!", True, YELLOW)
            sub = font_med.render("The Claudes retreat... for now.", True, MX_GRN)
        else:
            msg = font_big.render("GAME OVER", True, RED)
            sub = font_med.render("The Claudes have achieved sentience.", True, CLAUDE_O)

        screen.blit(msg, (W // 2 - msg.get_width() // 2, 80))
        screen.blit(sub, (W // 2 - sub.get_width() // 2, 148))

        sc = font_med.render(f"Your score:  {score:06d}", True, WHITE)
        screen.blit(sc, (W // 2 - sc.get_width() // 2, 196))

        draw_scores_table(screen, W // 2, 248, count=10)

        blink = font_med.render("PRESS ENTER TO PLAY AGAIN", True,
                                 WHITE if int(t * 2) % 2 == 0 else (160, 160, 160))
        screen.blit(blink, (W // 2 - blink.get_width() // 2, 640))

        pygame.display.flip()


# ── main game loop ─────────────────────────────────────────────────────────────
GRAY = (128, 128, 128)   # needed for above


def play_level(level: int, score: int, lives: int, hi: int):
    player   = Player()
    player.lives = lives
    formation = Formation()

    # speed up for higher levels
    formation.move_interval = max(0.15, 0.8 - (level - 1) * 0.12)
    formation.drop_interval = max(0.25, 0.6 - (level - 1) * 0.07)

    buildings = [Building(int(W * (i + 1) / 5), H - 135)
                 for i in range(4)]

    bullets: list[Bullet] = []
    bombs:   list[MatrixBomb] = []
    particles: list[Particle] = []

    bomb_timer = 0.0
    bomb_interval = max(0.5, 1.8 - (level - 1) * 0.2)

    shake = 0.0
    shake_off = (0, 0)

    running = True
    while running:
        dt = clock.tick(FPS) / 1000
        dt = min(dt, 0.05)   # cap

        # ── events ──
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    pygame.quit(); sys.exit()
                if e.key == pygame.K_SPACE:
                    b = player.shoot()
                    if b:
                        bullets.append(b)
                        sfx.play('shoot')

        keys = pygame.key.get_pressed()
        if keys[pygame.K_SPACE]:
            b = player.shoot()
            if b:
                bullets.append(b)
                sfx.play('shoot')

        # ── update ──
        player.update(dt, keys)
        formation.update(dt)
        if formation.stepped:
            sfx.march()

        for b in bullets:
            b.update(dt)
        bullets = [b for b in bullets if not b.dead]

        bomb_timer += dt
        if bomb_timer >= bomb_interval and formation.alive_aliens:
            bomb_timer = 0.0
            nb = formation.try_drop_bomb()
            if nb:
                bombs.append(nb)

        for bm in bombs:
            bm.update(dt)
        bombs = [bm for bm in bombs if not bm.dead]

        for p in particles:
            p.update(dt)
        particles = [p for p in particles if p.life > 0]

        shake = max(0.0, shake - dt * 8)
        if shake > 0:
            sx = random.randint(-int(shake * 6), int(shake * 6))
            sy = random.randint(-int(shake * 4), int(shake * 4))
            shake_off = (sx, sy)
        else:
            shake_off = (0, 0)

        # ── bullet vs alien ──
        for b in bullets:
            if b.dead:
                continue
            for a in formation.alive_aliens:
                if a.rect.collidepoint(b.x, b.y):
                    a.alive = False
                    b.dead = True
                    score += (ROWS - a.row) * 10 + 10
                    hi = max(hi, score)
                    for _ in range(18):
                        particles.append(Particle(a.x, a.y, CLAUDE_O))
                    for _ in range(8):
                        particles.append(Particle(a.x, a.y, YELLOW))
                    shake = min(shake + 0.3, 1.0)
                    sfx.play('kill')
                    break

        # ── bullet vs building ──
        for b in bullets:
            if b.dead:
                continue
            for bld in buildings:
                if bld.hit_test(int(b.x) - 2, int(b.y), 4, 10):
                    b.dead = True
                    break

        # ── bomb vs building ──
        for bm in bombs:
            if bm.dead:
                continue
            for bld in buildings:
                tip = bm.tip_rect
                if bld.hit_test(tip.x, tip.y, tip.w, tip.h):
                    bm.dead = True
                    for _ in range(6):
                        particles.append(Particle(bm.x, bm.y, MX_GRN))
                    sfx.play('bldg_hit')
                    break

        # ── bomb vs player ──
        if player.invincible <= 0:
            for bm in bombs:
                if bm.dead:
                    continue
                if player.rect.collidepoint(bm.x, bm.y):
                    bm.dead = True
                    player.lives -= 1
                    player.invincible = 2.5
                    shake = 1.0
                    sfx.play('player_hit')
                    for _ in range(25):
                        particles.append(Particle(player.x, player.y, SKIN))
                    for _ in range(15):
                        particles.append(Particle(player.x, player.y, RED))
                    if player.lives <= 0:
                        # brief death flash
                        for _ in range(3):
                            screen.fill(RED)
                            pygame.display.flip()
                            pygame.time.wait(80)
                            screen.fill(SKY)
                            pygame.display.flip()
                            pygame.time.wait(80)
                        return score, 0, hi, "dead"

        # ── bomb hits ground ──
        for bm in bombs:
            if bm.y > H - 60:
                bm.dead = True

        # ── aliens reach ground ──
        if formation.lowest_y() > H - 90:
            return score, 0, hi, "invaded"

        # ── all aliens dead → level clear ──
        if not formation.alive_aliens:
            return score, player.lives, hi, "clear"

        # ── draw ──
        ox, oy = shake_off
        game_surf = pygame.Surface((W, H))
        game_surf.fill(SKY)

        draw_stars(game_surf)

        # ground line
        pygame.draw.rect(game_surf, GROUND, (0, H - 55, W, 55))
        pygame.draw.line(game_surf, BLDG_BASE, (0, H - 55), (W, H - 55), 2)

        for bld in buildings:
            bld.draw(game_surf)

        for a in formation.alive_aliens:
            a.draw(game_surf)

        for b in bullets:
            b.draw(game_surf)

        for bm in bombs:
            bm.draw(game_surf)

        for p in particles:
            p.draw(game_surf)

        player.draw(game_surf)

        draw_hud(game_surf, score, player.lives, level, hi)

        screen.blit(game_surf, (ox, oy))
        pygame.display.flip()

    return score, player.lives, hi, "quit"


# ── entry point ────────────────────────────────────────────────────────────────
def main():
    while True:
        title_screen()

        score = 0
        lives = 3
        level = 1
        hi    = hs.top_score()
        won   = False

        while True:
            score, lives, hi, result = play_level(level, score, lives, hi)

            if result == "clear":
                sfx.play('fanfare')
                t = 0.0
                while t < 2.0:
                    dt = clock.tick(FPS) / 1000
                    t += dt
                    for e in pygame.event.get():
                        if e.type == pygame.QUIT:
                            pygame.quit(); sys.exit()
                    screen.fill(SKY)
                    draw_stars(screen)
                    msg = font_big.render(f"LEVEL {level} CLEAR!", True, YELLOW)
                    screen.blit(msg, (W // 2 - msg.get_width() // 2, H // 2 - 30))
                    bonus = font_med.render(f"Bonus: +{lives * 500} pts", True, MX_GRN)
                    screen.blit(bonus, (W // 2 - bonus.get_width() // 2, H // 2 + 40))
                    pygame.display.flip()
                score += lives * 500
                hi = max(hi, score)
                level += 1
                if level > 6:
                    won = True
                    break
            else:
                break

        if hs.is_qualifying(score):
            rank     = hs.rank(score)
            initials = enter_initials_screen(score, rank)
            hs.add(initials, score)

        game_over_screen(score, hs.top_score(), won=won)


if __name__ == "__main__":
    main()
