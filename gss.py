# -*- coding: utf-8 -*-

# Copyright (c) 2005 - 2021 Yasuaki Gohko
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE ABOVE LISTED COPYRIGHT HOLDER(S) BE LIABLE FOR ANY CLAIM, DAMAGES OR
# OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
# ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.

import copy
import random
import math
import pickle
import sys

import pygame

import numpy as np

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim

enemy_rand = random.Random()
enemy_rand.seed(123)
effect_rand = random.Random()
effect_rand.seed(456)
agent_rand = random.Random()
agent_rand.seed(789)

VERSION = "0.0.0"
SCREEN_WIDTH = 640
SCREEN_HEIGHT = 480
FIXED_MUL = 16384
FIXED_WIDTH = SCREEN_WIDTH * FIXED_MUL
FIXED_HEIGHT = SCREEN_HEIGHT * FIXED_MUL
JOYSTICK_THRESHOLD = 0.5


def ScreenInt(val):
    return int(val / FIXED_MUL)


def Fixed(val):
    return int(val * FIXED_MUL)


def Sign(val):
    if val > 0:
        return 1
    elif val < 0:
        return -1
    return 0


def Radian(deg):
    return (deg * 2.0 * math.pi) / 360.0


def RandomEnemyVector(length):
    x = (enemy_rand.randrange(128) + 1) * (enemy_rand.randrange(2) * 3 - 1)
    y = (enemy_rand.randrange(128) + 1) * (enemy_rand.randrange(2) * 3 - 1)
    current_length = math.sqrt(x * x + y * y)
    x = int(float(x) * length / current_length)
    y = int(float(y) * length / current_length)
    return (x, y)


def RandomEffectVector(length):
    x = (effect_rand.randrange(128) + 1) * (effect_rand.randrange(2) * 3 - 1)
    y = (effect_rand.randrange(128) + 1) * (effect_rand.randrange(2) * 3 - 1)
    current_length = math.sqrt(x * x + y * y)
    x = int(float(x) * length / current_length)
    y = int(float(y) * length / current_length)
    return (x, y)


class Settings:
    def __init__(self):
        self.no_wait = False
        self.silent = False
        self.frame_skipping = False
        self.elite_skipping = False

    def GetNoWait(self):
        return self.no_wait

    def SetNoWait(self, no_wait):
        self.no_wait = no_wait

    def GetSilent(self):
        return self.silent

    def SetSilent(self, silent):
        self.silent = silent

    def GetFrameSkipping(self):
        return self.frame_skipping

    def SetFrameSkipping(self, frame_skipping):
        self.frame_skipping = frame_skipping

    def GetEliteSkipping(self):
        return self.elite_skipping

    def SetEliteSkipping(self, elite_skipping):
        self.elite_skipping = elite_skipping


class Sprite:
    def __init__(self, surface, offset_x, offset_y, width, height):
        self.surface = surface
        self.offset_x = offset_x
        self.offset_y = offset_y
        self.width = width
        self.height = height
        self.rect = (0, 0, width, height)

    def Draw(self, screen_surface, x, y):
        screen_surface.blit(self.surface, (ScreenInt(x) + self.offset_x, ScreenInt(y) + self.offset_y), self.rect)

    def SetFrame(self, frame_num):
        self.rect = (self.width * frame_num, 0, self.width, self.height)


class Collision:
    def __init__(self, min_x, min_y, max_x, max_y):
        self.min_x = min_x
        self.min_y = min_y
        self.max_x = max_x
        self.max_y = max_y

    def Check(self, x, y, other, other_x, other_y):
        self_min_x = x + self.min_x
        self_min_y = y + self.min_y
        self_max_x = x + self.max_x
        self_max_y = y + self.max_y
        other_min_x = other_x + other.min_x
        other_min_y = other_y + other.min_y
        other_max_x = other_x + other.max_x
        other_max_y = other_y + other.max_y
        if (self_min_x <= other_min_x <= self_max_x
            or self_min_x <= other_max_x <= self_max_x
            or other_min_x <= self_min_x <= other_max_x
            or other_min_x <= self_max_x <= other_max_x) \
                and (self_min_y <= other_min_y <= self_max_y
                     or self_min_y <= other_max_y <= self_max_y
                     or other_min_y <= self_min_y <= other_max_y
                     or other_min_y <= self_max_y <= other_max_y):
            return True
        return False

    def CheckSceneOut(self, x, y):
        if (x + self.max_x) < 0 \
                or (x + self.min_x) > FIXED_WIDTH \
                or (y + self.max_y) < 0 \
                or (y + self.min_y) > FIXED_HEIGHT:
            return True
        return False

    def RoundToSceneLimit(self, x, y):
        if (x + self.min_x) < 0:
            x = 0 - self.min_x
        if (x + self.max_x) > FIXED_WIDTH:
            x = FIXED_WIDTH - self.max_x
        if (y + self.min_y) < 0:
            y = 0 - self.min_y
        if (y + self.max_y) > FIXED_HEIGHT:
            y = FIXED_HEIGHT - self.max_y
        return x, y


class PointCollision(Collision):
    def Check(self, x, y, other, other_x, other_y):
        if (other_x + other.min_x < x < other_x + other.max_x) \
                and (other_y + other.min_y < y < other_y + other.max_y):
            return True
        return False


class Actor:
    def __init__(self):
        self.x = 0
        self.y = 0
        self.sprite = Sprite(Gss.data.enemy_surface, -16, -16, 32, 32)

    def Process(self):
        pass

    def Draw(self, screen_surface):
        self.sprite.Draw(screen_surface, self.x, self.y)

    def CheckCollision(self, other):
        return self.collision.Check(self.x, self.y, other.collision, other.x, other.y)

    def CheckSceneOut(self):
        return self.collision.CheckSceneOut(self.x, self.y)

    def Search(self, other):
        angle = math.atan2(other.y - self.y, other.x - self.x)
        if angle < 0.0:
            angle += 2 * math.pi
        return angle


class Player(Actor):
    APPEAR = 0
    MOVE = 1
    DESTROY = 2

    def __init__(self):
        Actor.__init__(self)
        self.sprite = Sprite(Gss.data.player_surface, -16, -16, 32, 32)
        self.collision = Collision(Fixed(-8), Fixed(-8), Fixed(8), Fixed(8))
        self.state = Player.APPEAR
        self.nocol_cnt = 0
        self.gen = self.Appear()

    def Process(self):
        self.gen.__next__()

    def Draw(self, screen_surface):
        if self.state == Player.APPEAR \
                or (self.state == Player.MOVE and (self.nocol_cnt & 1) == 0):
            Actor.Draw(self, screen_surface)

    def Appear(self):
        self.x = Fixed(0)
        self.y = Fixed(480)
        yield None
        smoke_cnt = 0
        velocity_x = Fixed(16)
        for i in range(30):
            velocity_x -= Fixed(1)
            self.x += velocity_x + Fixed(2)
            self.y -= Fixed(10)
            smoke_cnt += 1
            smoke_cnt &= 1
            if smoke_cnt == 0:
                Shooting.scene.explosions.Append(Smoke(self.x, self.y, Fixed(-18) + Fixed(effect_rand.randrange(3) - 1), Fixed(effect_rand.randrange(3) - 1)))
            yield None
        self.state = Player.MOVE
        self.nocol_cnt = 120
        self.gen = self.Move()
        yield None

    def Move(self):
        shot_cnt = 0
        living_cnt = 0
        agent = Gss.agents[Gss.agent_index]
        while True:
            pressed = Gss.joystick.GetPressed()
            if pressed & Joystick.RIGHT:
                self.x += Fixed(5)
            if pressed & Joystick.LEFT:
                self.x -= Fixed(5)
            if pressed & Joystick.UP:
                self.y -= Fixed(5)
            if pressed & Joystick.DOWN:
                self.y += Fixed(5)
            old_x = self.x
            old_y = self.y
            self.x, self.y = self.collision.RoundToSceneLimit(self.x, self.y)
            if self.x != old_x or self.y != old_y:
                pass
                # agent.SetCurrentReward(0.1)
                # Shooting.scene.status.UpdatePenalty(0.1)
            living_cnt += 1
            if self.x > Fixed(320):
                pass
                # agent.SetCurrentReward(0.1)
            shot_cnt += 1
            shot_cnt &= 3
            synchro_shot_cnt = shot_cnt & 1
            if ((pressed & Joystick.A and shot_cnt == 0) or (pressed & Joystick.B and synchro_shot_cnt == 0)):
                if Shooting.scene.beams.Append(Beam(self.x, self.y)) == True:
                    if not Gss.settings.GetSilent():
                        Gss.data.beam_sound.play()
            if self.nocol_cnt > 0:
                self.nocol_cnt -= 1
            event_velocity = (ScreenInt(self.x) - SCREEN_WIDTH / 3) / 4
            Shooting.scene.status.AddEventSpeed(event_velocity)
            yield None

    def Destroy(self):
        for i in range(30):
            yield None
        player_stock = Shooting.scene.status.DecrementPlayerStock(1)

        if Shooting.scene.status.GetCompleted() == True:
            Shooting.scene.gameoverstring = GameOverString()
            while True:
                yield None
        self.state = Player.APPEAR
        self.gen = self.Appear()
        self.Process()
        yield None

    def AddDamage(self, damage):
        Shooting.scene.status.ResetMultilier()
        if not Gss.settings.GetSilent():
            Gss.data.explosion_large_sound.play()
        for i in range(10):
            velocity = RandomEffectVector(Fixed(effect_rand.randrange(8)))
            Shooting.scene.explosions.Append(PlayerExplosion(self.x, self.y, velocity[0], velocity[1]))
        self.state = Player.DESTROY
        self.gen = self.Destroy()

    def Suicide(self):
        score = Shooting.scene.status.AddSuicideScore()
        Shooting.scene.status.DecrementPlayerStock(3)
        Shooting.scene.player.AddDamage(1)

    def HasCollision(self):
        if self.state == Player.MOVE and self.nocol_cnt == 0:
            return True
        return False


class Beam(Actor):
    def __init__(self, x, y):
        Actor.__init__(self)
        self.x = x
        self.y = y
        self.cnt = 0
        self.sprite = Sprite(Gss.data.beam_surface, -16, -16, 48, 32)
        self.collision = Collision(Fixed(-16), Fixed(-16), Fixed(16), Fixed(16))

    def Process(self):
        self.cnt += 1
        self.cnt &= 1
        self.x += Fixed(16)
        self.sprite.SetFrame(self.cnt)
        if self.CheckSceneOut() == True:
            Shooting.scene.beams.Remove(self)


class Enemy(Actor):
    APPEAR = 0
    MOVE = 1
    DESTROY = 2

    def __init__(self):
        Actor.__init__(self)
        self.x = 0
        self.y = 0
        self.velocity_x = 0
        self.velocity_y = 0
        self.shield = 1
        self.live_cnt = 0
        self.state = Enemy.MOVE
        self.sprite = Sprite(Gss.data.enemy_surface, -16, -16, 32, 32)
        self.collision = Collision(Fixed(-16), Fixed(-16), Fixed(16), Fixed(16))

    def Process(self):
        self.live_cnt += 1
        if self.CheckSceneOut() == True:
            Shooting.scene.enemies.Remove(self)

    def AddDamage(self, damage):
        self.shield -= damage
        Shooting.scene.status.AddScore(1)
        if self.shield <= 0:
            # スコア更新
            Shooting.scene.status.UpdateMultiplier(self.live_cnt)
            Shooting.scene.status.AddScore(100)

            # 死
            if not Gss.settings.GetSilent():
                Gss.data.explosion_small_sound.play()
            type = effect_rand.randrange(10)
            if type < 8:
                velocity = RandomEffectVector(Fixed(effect_rand.randrange(8)) / 8)
                velocity_x = self.velocity_x + velocity[0]
                velocity_y = self.velocity_y + velocity[1]
                Shooting.scene.explosions.Append(Explosion(self.x, self.y, velocity_x, velocity_y))
            elif type == 8:
                for i in range(8):
                    velocity = RandomEffectVector(Fixed(effect_rand.randrange(8)))
                    velocity_x = self.velocity_x + velocity[0]
                    velocity_y = self.velocity_y + velocity[1]
                    Shooting.scene.explosions.Append(Explosion(self.x, self.y, velocity_x, velocity_y))
            else:
                base_velocity = RandomEffectVector(Fixed(2))
                for i in range(8):
                    velocity = RandomEffectVector(Fixed(1))
                    velocity_x = self.velocity_x + base_velocity[0] * i + velocity[0]
                    velocity_y = self.velocity_y + base_velocity[1] * i + velocity[1]
                    Shooting.scene.explosions.Append(Explosion(self.x, self.y, velocity_x, velocity_y))
            Shooting.scene.enemies.Remove(self)

    def HasCollision(self):
        if self.state == Enemy.MOVE:
            return True
        return False


class StraightEnemy(Enemy):
    def __init__(self, x, y):
        Enemy.__init__(self)
        self.x = x
        self.y = y
        self.velocity_x = Fixed(-7)
        if self.y < Fixed(240):
            self.velocity_y = Fixed(1)
        else:
            self.velocity_y = Fixed(-1)
        self.gen = self.Move()

    def Process(self):
        self.gen.__next__()
        Enemy.Process(self)

    def Move(self):
        cnt = 0
        while True:
            self.velocity_x += Fixed(0.035)
            self.x += self.velocity_x
            self.y += self.velocity_y
            cnt += 1
            if cnt == 50 or cnt == 100:
                Shooting.scene.bullets.Append(Bullet.FromAngle(self.x, self.y, self.Search(Shooting.scene.player), 5))
            yield None


class StraightBulletEnemy(Enemy):
    def __init__(self, x, y):
        Enemy.__init__(self)
        self.x = x
        self.y = y
        self.velocity_x = Fixed(-5)
        if self.y < Fixed(240):
            self.velocity_y = Fixed(0.1)
        else:
            self.velocity_y = Fixed(-0.1)
        self.gen = self.Move()

    def Process(self):
        self.gen.__next__()
        Enemy.Process(self)

    def Move(self):
        cnt = 0
        while True:
            self.velocity_x -= Fixed(0.05)
            self.x += self.velocity_x
            self.y += self.velocity_y
            cnt += 1
            if (cnt & 7) == 0:
                Shooting.scene.bullets.Append(Bullet(self.x, self.y, Fixed(enemy_rand.randrange(5) + 0.2), Fixed(enemy_rand.randrange(4) * 2 - 3)))
            yield None


class StayEnemy(Enemy):
    def __init__(self, x, y, velocity_y):
        Enemy.__init__(self)
        self.x = x
        self.y = y
        self.velocity_x = Fixed(-5)
        self.velocity_y = velocity_y
        self.gen = self.Move()

    def Process(self):
        self.gen.__next__()
        Enemy.Process(self)

    def Move(self):
        cnt = 0
        while True:
            if cnt < 180:
                if self.velocity_x < Fixed(-1):
                    self.velocity_x += Fixed(0.1)
            else:
                self.velocity_x -= Fixed(0.1)
            self.x += self.velocity_x
            self.y += self.velocity_y
            cnt += 1
            if cnt > 60 and (cnt & 31) == 0:
                Shooting.scene.bullets.Append(Bullet(self.x, self.y, Fixed(-5), Fixed(enemy_rand.randrange(7) - 3)))
            yield None


class RollEnemy(Enemy):
    def __init__(self, x, y):
        Enemy.__init__(self)
        self.x = x
        self.y = y
        self.velocity_x = Fixed(-5)
        self.velocity_y = Fixed(0)
        if self.y < Fixed(240):
            self.direction = -1
        else:
            self.direction = 1
        self.gen = self.Move()

    def Process(self):
        self.gen.__next__()
        Enemy.Process(self)

    def Move(self):
        cnt = 0
        for angle in self.Roll():
            self.velocity_x = Fixed(math.cos(angle) * -5.0)
            self.velocity_y = Fixed(math.sin(angle) * -5.0 * self.direction)
            self.x += self.velocity_x
            self.y += self.velocity_y
            cnt += 1
            if (cnt & 63) == 0:
                Shooting.scene.bullets.Append(Bullet.FromAngle(self.x, self.y, self.Search(Shooting.scene.player), 5))
            yield None

    def Roll(self):
        for i in range(60):
            yield 0.0
        for i in range(225):
            yield Radian(i * 1.2)
        while True:
            yield Radian(270.0)


class BackwordEnemy(Enemy):
    def __init__(self, x, y):
        Enemy.__init__(self)
        self.x = x
        self.y = y
        self.velocity_x = Fixed(7)
        if self.y < Fixed(240):
            self.velocity_y = Fixed(1)
        else:
            self.velocity_y = Fixed(-1)
        self.gen = self.Move()

    def Process(self):
        self.gen.__next__()
        Enemy.Process(self)

    def Move(self):
        cnt = 0
        while True:
            if self.velocity_x > Fixed(1):
                self.velocity_x -= Fixed(0.045)
            else:
                self.velocity_y += Fixed(Sign(self.velocity_y) * 0.05)
            self.x += self.velocity_x
            self.y += self.velocity_y
            cnt += 1
            if cnt >= 120 and (cnt & 31) == 0:
                for bullet in Bullet.FromAngle3Way(self.x, self.y, self.Search(Shooting.scene.player), Radian(12), 5):
                    Shooting.scene.bullets.Append(bullet)
            yield None


class VerticalMissileEnemy(Enemy):
    def __init__(self, x, y):
        Enemy.__init__(self)
        self.x = x
        self.y = y
        self.velocity_x = Fixed(-5)
        if self.y < Fixed(240):
            self.velocity_y = Fixed(0.2)
        else:
            self.velocity_y = Fixed(-0.2)
        self.gen = self.Move()

    def Process(self):
        self.gen.__next__()
        Enemy.Process(self)

    def Move(self):
        done = False
        while done == False:
            self.x += self.velocity_x
            self.y += self.velocity_y
            if self.x < (Shooting.scene.player.x + Fixed(32)):
                done = True
            yield None
        for i in range(16):
            self.velocity_x = int((Shooting.scene.player.x - self.x) * 0.1)
            self.x += self.velocity_x
            self.y += self.velocity_y
            yield None
        self.x += self.velocity_x
        self.y += self.velocity_y
        if self.y < Shooting.scene.player.y:
            angle = Radian(90)
        else:
            angle = Radian(270)
        if not Gss.settings.GetSilent():
            Gss.data.missile_sound.play()
        Shooting.scene.enemies.Append(Missile(self.x, self.y, angle))
        yield None
        while True:
            self.velocity_x -= Fixed(0.1)
            self.x += self.velocity_x
            self.y += self.velocity_y
            yield None


class StraightMissileEnemy(Enemy):
    def __init__(self, x, y):
        Enemy.__init__(self)
        self.x = x
        self.y = y
        self.velocity_x = Fixed(-7)
        self.velocity_y = 0
        self.gen = self.Move()

    def Process(self):
        self.gen.__next__()
        Enemy.Process(self)

    def Move(self):
        shoot = False
        while True:
            self.velocity_x += Fixed(0.1)
            self.x += self.velocity_x
            self.y += self.velocity_y
            if self.velocity_x > 0 and shoot == False:
                shoot = True
                if not Gss.settings.GetSilent():
                    Gss.data.missile_sound.play()
                Shooting.scene.enemies.Append(Missile(self.x, self.y, Radian(180)))
            yield None


class MiddleEnemy(Enemy):
    def __init__(self, x, y):
        Enemy.__init__(self)
        self.x = x
        self.y = y
        self.velocity_x = Fixed(-5)
        self.shield = 32
        self.gen = self.Move()
        self.sprite = Sprite(Gss.data.middleenemy_surface, -64, -64, 128, 128)
        self.collision = Collision(Fixed(-64), Fixed(-64), Fixed(64), Fixed(64))

    def Process(self):
        self.gen.__next__()
        Enemy.Process(self)

    def Move(self):
        shoot_gen = self.Shoot()
        for i in range(480):
            if self.velocity_x < Fixed(-1):
                self.velocity_x += Fixed(0.1)
            self.x += self.velocity_x
            self.y += self.velocity_y
            shoot_gen.__next__()
            yield None
        while True:
            self.velocity_x -= Fixed(0.1)
            self.x += self.velocity_x
            self.y += self.velocity_y
            shoot_gen.__next__()
            yield None

    def Destroy(self):
        for i in range(120):
            self.velocity_y += Fixed(0.005)
            self.x += self.velocity_x
            self.y += self.velocity_y
            if effect_rand.randrange(16) == 0:
                if not Gss.settings.GetSilent():
                    Gss.data.explosion_small_sound.play()
            if effect_rand.randrange(8) == 0:
                x = self.x + Fixed(effect_rand.randrange(64) - 32)
                y = self.y + Fixed(effect_rand.randrange(64) - 32)
                velocity = RandomEffectVector(Fixed(effect_rand.randrange(8)))
                Shooting.scene.explosions.Append(Explosion(x, y, velocity[0], velocity[1]))
            yield None
        if not Gss.settings.GetSilent():
            Gss.data.explosion_sound.play()
        for i in range(8):
            velocity = RandomEffectVector(Fixed(effect_rand.randrange(8)))
            x = self.x + velocity[0] * 3
            y = self.y + velocity[1] * 3
            Shooting.scene.explosions.Append(BigExplosion(x, y, velocity[0], velocity[1]))
        Shooting.scene.enemies.Remove(self)
        yield None

    def Shoot(self):
        for i in range(120):
            yield None
        interval = 26
        while True:
            for i in range(interval):
                yield None
            Shooting.scene.bullets.Append(Bullet.FromAngle(self.x, self.y, self.Search(Shooting.scene.player) + Radian(enemy_rand.randrange(32) - 16), 5))
            interval -= 1
            if interval <= 0:
                interval = 1

    def AddDamage(self, damage):
        self.shield -= damage
        Shooting.scene.status.AddScore(1)
        if self.shield <= 0:
            # スコア更新
            Shooting.scene.status.UpdateMultiplier(self.live_cnt)
            Shooting.scene.status.AddScore(1000)

            self.state = Enemy.DESTROY
            self.gen = self.Destroy()


class MiddleMissileEnemy(MiddleEnemy):
    def __init__(self, x, y):
        MiddleEnemy.__init__(self, x, y)

    def Process(self):
        self.gen.__next__()
        Enemy.Process(self)

    def Move(self):
        cnt = 0
        for i in range(480):
            if self.velocity_x < Fixed(-1):
                self.velocity_x += Fixed(0.1)
            self.x += self.velocity_x
            self.y += self.velocity_y
            cnt += 1
            if cnt > 180 and (cnt % 80) == 0:
                if not Gss.settings.GetSilent():
                    Gss.data.missile_sound.play()
                Shooting.scene.enemies.Append(Missile(self.x, self.y, Radian(240)))
                Shooting.scene.enemies.Append(Missile(self.x, self.y, Radian(210)))
                Shooting.scene.enemies.Append(Missile(self.x, self.y, Radian(150)))
                Shooting.scene.enemies.Append(Missile(self.x, self.y, Radian(120)))
            yield None
        while True:
            self.velocity_x -= Fixed(0.1)
            self.x += self.velocity_x
            self.y += self.velocity_y
            yield None


class BossEnemy(Enemy):
    GRANDCHILD_INDEX_LIST = (None, None, 4, 5, None, None)
    PAIR_CHILD_INDEX_LIST = (None, None, 3, 2, 5, 4)

    def __init__(self, x, y):
        Enemy.__init__(self)
        self.x = x
        self.y = y
        self.velocity_x = Fixed(-1.60)
        self.velocity_y = Fixed(-8)
        self.shield = 192
        self.gen = self.Appear()
        self.watch_children_gen = self.WatchChildren()
        self.sprite = Sprite(Gss.data.bossenemy_surface, -128, -128, 256, 256)
        self.collision = Collision(Fixed(-128), Fixed(-128), Fixed(128), Fixed(128))
        self.children = [BossBatteryEnemy(Fixed(-64), Fixed(-128 - 16), self), BossBatteryEnemy(Fixed(-64), Fixed(128 + 16), self), BossSpreadBulletEnemy(Fixed(64), Fixed(-128 - 16), self),
                         BossSpreadBulletEnemy(Fixed(64), Fixed(128 + 16), self), BossMissileEnemy(Fixed(80), Fixed(-128 - 48), self), BossMissileEnemy(Fixed(80), Fixed(128 + 48), self)]
        for child in self.children:
            Shooting.scene.enemies.Append(child)

    def Process(self):
        self.gen.__next__()
        self.watch_children_gen.__next__()
        for child in self.children:
            if child != None:
                child.UpdatePosition()

    def SplitChild(self, child):
        for i in range(len(self.children)):
            if self.children[i] is child:
                self.children[i] = None
                grandchild_index = BossEnemy.GRANDCHILD_INDEX_LIST[i]
                if grandchild_index != None:
                    grandchild = self.children[grandchild_index]
                    if grandchild != None:
                        self.SplitChild(grandchild)
                        grandchild.SplitFromBoss()

    def Appear(self):
        for i in range(160):
            self.velocity_x += Fixed(0.01)
            self.velocity_y += Fixed(0.05)
            self.x += self.velocity_x
            self.y += self.velocity_y
            yield None
        self.gen = self.Move()
        self.velocity_x = 0
        self.velocity_y += Fixed(0.05)
        self.target_velocity_y = Fixed(1.5)
        self.x += self.velocity_x
        self.y += self.velocity_y
        yield None

    def Move(self):
        while True:
            for i in range(120):
                if self.y < Fixed(120):
                    self.target_velocity_y = Fixed(1.5)
                else:
                    if self.y > Fixed(360):
                        self.target_velocity_y = Fixed(-1.5)
                if self.velocity_y < self.target_velocity_y:
                    self.velocity_y += Fixed(0.02)
                else:
                    if self.velocity_y > self.target_velocity_y:
                        self.velocity_y += Fixed(-0.02)
                self.x += self.velocity_x
                self.y += self.velocity_y
                yield None
            for i in range(60):
                if self.velocity_y < self.target_velocity_y:
                    self.velocity_y += Fixed(0.02)
                else:
                    if self.velocity_y > self.target_velocity_y:
                        self.velocity_y += Fixed(-0.02)
                self.x += self.velocity_x
                self.y += self.velocity_y
                if (i & 1) == 0:
                    velocity = RandomEffectVector(Fixed(effect_rand.randrange(4)))
                    Shooting.scene.explosions.Append(BulletExplosion(self.x - Fixed(128), self.y + Fixed(effect_rand.randrange(256) - 128), Fixed(-4) + velocity[0], Fixed(0) + velocity[1]))
                yield None
            for i in range(60):
                if self.velocity_y < self.target_velocity_y:
                    self.velocity_y += Fixed(0.02)
                else:
                    if self.velocity_y > self.target_velocity_y:
                        self.velocity_y += Fixed(-0.02)
                self.x += self.velocity_x
                self.y += self.velocity_y
                Shooting.scene.bullets.Append(LongBullet(self.x - Fixed(128), self.y + Fixed(enemy_rand.randrange(256) - 128), Fixed(-16), Fixed(0)))
                yield None

    def GoBerserk(self):
        while True:
            for i in range(60):
                velocity_y = int((Shooting.scene.player.y - self.y) * 0.015)
                self.velocity_y += int((velocity_y - self.velocity_y) * 0.05)
                self.x += self.velocity_x
                self.y += self.velocity_y
                if (i & 1) == 0:
                    velocity = RandomEffectVector(Fixed(effect_rand.randrange(4)))
                    Shooting.scene.explosions.Append(BulletExplosion(self.x - Fixed(128), self.y + Fixed(effect_rand.randrange(256) - 128), Fixed(-4) + velocity[0], Fixed(0) + velocity[1]))
                yield None
            for i in range(60):
                self.x += self.velocity_x
                self.y += self.velocity_y
                Shooting.scene.bullets.Append(LongBullet(self.x - Fixed(128), self.y + Fixed(enemy_rand.randrange(256) - 128), Fixed(-16), Fixed(0)))
                yield None
            for i in range(45):
                self.x += self.velocity_x
                self.y += self.velocity_y
                yield None

    def Damage(self):
        for i in range(120):
            self.velocity_x = int(self.velocity_x * 0.95)
            self.velocity_y = int(self.velocity_y * 0.95)
            self.x += self.velocity_x
            self.y += self.velocity_y
            yield None

        has_splited_child = False
        for i in range(len(self.children)):
            child = self.children[i]
            if child == None:
                pair_child_index = BossEnemy.PAIR_CHILD_INDEX_LIST[i]
                if pair_child_index != None:
                    pair_child = self.children[pair_child_index]
                    if pair_child != None:
                        self.SplitChild(pair_child)
                        pair_child.SplitFromBoss()
                        has_splited_child = True
        if has_splited_child == True:
            for i in range(30):
                self.velocity_x = int(self.velocity_x * 0.95)
                self.velocity_y = int(self.velocity_y * 0.95)
                self.x += self.velocity_x
                self.y += self.velocity_y
                yield None

        has_child = False
        for child in self.children:
            if child != None:
                has_child = True

        if has_child == True:
            self.gen = self.Move()
        else:
            self.gen = self.GoBerserk()
        self.x += self.velocity_x
        self.y += self.velocity_y
        yield None

    def Destroy(self):
        for i in range(180):
            self.velocity_y = (self.velocity_y * 254) / 256
            self.x += self.velocity_x
            self.y += self.velocity_y
            if effect_rand.randrange(16) == 0:
                if not Gss.settings.GetSilent():
                    Gss.data.explosion_small_sound.play()
            if effect_rand.randrange(3) == 0:
                x = self.x + Fixed(effect_rand.randrange(128) - 64)
                y = self.y + Fixed(effect_rand.randrange(128) - 64)
                velocity = RandomEffectVector(Fixed(effect_rand.randrange(8)))
                Shooting.scene.explosions.Append(Explosion(x, y, velocity[0], velocity[1]))
            yield None
        if not Gss.settings.GetSilent():
            Gss.data.explosion_sound.play()
        for i in range(64):
            velocity = RandomEffectVector(Fixed(effect_rand.randrange(24)))
            x = self.x + velocity[0] * 3
            y = self.y + velocity[1] * 3
            Shooting.scene.explosions.Append(BigExplosion(x, y, velocity[0], velocity[1]))
        Shooting.scene.enemies.Remove(self)
        yield None

    def WatchChildren(self):
        while True:
            battery_enemy_exists = False
            for child in self.children:
                if child != None:
                    if child.GetType() == BossPartEnemy.BOSS_BATTERY_ENEMY:
                        battery_enemy_exists = True
                        child.ToMove()
            if battery_enemy_exists == True:
                for i in range(128):
                    yield None
                for child in self.children:
                    if child != None:
                        child.ToIdle()
                for i in range(64):
                    yield None
            spreadbullet_enemy_exists = False
            for child in self.children:
                if child != None:
                    if child.GetType() == BossPartEnemy.BOSS_SPREADBULLET_ENEMY:
                        spreadbullet_enemy_exists = True
                        child.ToMove()
            if spreadbullet_enemy_exists == True:
                for i in range(128):
                    yield None
                for child in self.children:
                    if child != None:
                        child.ToIdle()
                for i in range(64):
                    yield None
            missile_enemy_exists = False
            for child in self.children:
                if child != None:
                    if child.GetType() == BossPartEnemy.BOSS_MISSILE_ENEMY:
                        missile_enemy_exists = True
                        child.ToMove()
            if missile_enemy_exists == True:
                for i in range(128):
                    yield None
                for child in self.children:
                    if child != None:
                        child.ToIdle()
                for i in range(64):
                    yield None
            if battery_enemy_exists == False and missile_enemy_exists == False:
                yield None

    def AddDamage(self, damage):
        self.shield -= damage
        Shooting.scene.status.AddScore(1)
        if self.shield <= 0:
            # スコア更新
            Shooting.scene.status.UpdateMultiplier(self.live_cnt)
            Shooting.scene.status.AddScore(10000)

            # 死
            children = self.children[:]
            for child in self.children:
                if child != None:
                    self.SplitChild(child)
                    child.SplitFromBoss()
            for child in children:
                if child != None:
                    child.ToDestroy()
            self.state = Enemy.DESTROY
            self.gen = self.Destroy()

    def ToDamage(self, inc_velocity_x, inc_velocity_y):
        self.velocity_x += inc_velocity_x
        self.velocity_y += inc_velocity_y
        self.gen = self.Damage()


class BossPartEnemy(Enemy):
    BOSS_PART_ENEMY = 0
    BOSS_BATTERY_ENEMY = 1
    BOSS_MISSILE_ENEMY = 2
    BOSS_SPREADBULLET_ENEMY = 3

    def __init__(self, x, y, parent):
        Enemy.__init__(self)
        self.offset_x = x
        self.offset_y = y
        self.parent = parent
        self.type = BossPartEnemy.BOSS_PART_ENEMY
        self.x = self.parent.x
        self.y = self.parent.y
        self.velocity_x = parent.velocity_x
        self.velocity_y = parent.velocity_y

    def Process(self):
        if self.parent == None and self.CheckSceneOut() == True:
            Shooting.scene.enemies.Remove(self)

    def UpdatePosition(self):
        self.x = self.parent.x + self.offset_x
        self.y = self.parent.y + self.offset_y
        self.velocity_x = self.parent.velocity_x
        self.velocity_y = self.parent.velocity_y

    def SplitFromBoss(self):
        self.parent = None
        self.gen = self.Fall()

    def Fall(self):
        if self.offset_y > 0:
            direction_y = Fixed(0.005)
        else:
            direction_y = Fixed(-0.005)
        self.velocity_x = Fixed(-0.5)
        while True:
            self.velocity_y += direction_y
            self.x += self.velocity_x
            self.y += self.velocity_y
            yield None

    def AddDamage(self, damage):
        self.shield -= damage
        Shooting.scene.status.AddScore(1)
        if self.shield <= 0:
            # スコア更新
            Shooting.scene.status.UpdateMultiplier(self.live_cnt)
            Shooting.scene.status.AddScore(100)

            # 死
            self.ToDestroy()

    def ToDestroy(self):
        if self.parent != None:
            if not Gss.settings.GetSilent():
                Gss.data.explosion_sound.play()
            for i in range(16):
                velocity = RandomEffectVector(Fixed(effect_rand.randrange(12)))
                Shooting.scene.explosions.Append(Explosion(self.x, self.y, velocity[0], velocity[1]))
            if self.offset_y > 0:
                inc_velocity_y = Fixed(-4)
            else:
                inc_velocity_y = Fixed(4)
            self.parent.ToDamage(0, inc_velocity_y)
            self.parent.SplitChild(self)
            self.SplitFromBoss()
        if not Gss.settings.GetSilent():
            Gss.data.explosion_small_sound.play()
        Shooting.scene.explosions.Append(Explosion(self.x, self.y, self.velocity_x, self.velocity_y))
        Shooting.scene.enemies.Remove(self)

    def GetType(self):
        return self.type


class BossBatteryEnemy(BossPartEnemy):
    def __init__(self, x, y, parent):
        BossPartEnemy.__init__(self, x, y, parent)
        self.type = BossPartEnemy.BOSS_BATTERY_ENEMY
        self.shield = 24
        self.gen = self.Idle()

    def Process(self):
        self.gen.__next__()
        BossPartEnemy.Process(self)

    def Move(self):
        while True:
            for j in range(31):
                yield None
            Shooting.scene.bullets.Append(Bullet.FromAngle(self.x, self.y, self.Search(Shooting.scene.player), 5))
            yield None

    def Idle(self):
        while True:
            yield None

    def ToMove(self):
        self.gen = self.Move()

    def ToIdle(self):
        self.gen = self.Idle()


class BossMissileEnemy(BossPartEnemy):
    def __init__(self, x, y, parent):
        BossPartEnemy.__init__(self, x, y, parent)
        self.type = BossPartEnemy.BOSS_MISSILE_ENEMY
        self.shield = 24
        self.gen = self.Idle()

    def Process(self):
        self.gen.__next__()
        BossPartEnemy.Process(self)

    def Move(self):
        while True:
            for j in range(31):
                yield None
            if not Gss.settings.GetSilent():
                Gss.data.missile_sound.play()
            Shooting.scene.enemies.Append(Missile(self.x, self.y, Radian(180)))
            yield None

    def Idle(self):
        while True:
            yield None

    def ToMove(self):
        self.gen = self.Move()

    def ToIdle(self):
        self.gen = self.Idle()


class BossSpreadBulletEnemy(BossPartEnemy):
    def __init__(self, x, y, parent):
        BossPartEnemy.__init__(self, x, y, parent)
        self.type = BossPartEnemy.BOSS_SPREADBULLET_ENEMY
        self.shield = 24
        self.gen = self.Idle()

    def Process(self):
        self.gen.__next__()
        BossPartEnemy.Process(self)

    def Move(self):
        while True:
            for j in range(63):
                yield None
            for bullet in Bullet.FromAngleSpread(self.x, self.y, self.Search(Shooting.scene.player), 2, 1, 10):
                Shooting.scene.bullets.Append(bullet)
            yield None
            for j in range(64):
                yield None

    def Idle(self):
        while True:
            yield None

    def ToMove(self):
        self.gen = self.Move()

    def ToIdle(self):
        self.gen = self.Idle()


class Missile(Enemy):
    def __init__(self, x, y, angle):
        Enemy.__init__(self)
        self.x = x
        self.y = y
        self.angle = angle
        self.velocity_x = 0
        self.velocity_y = 0
        self.sprite = Sprite(Gss.data.missile_surface, -15, -15, 32, 32)
        self.collision = Collision(Fixed(-2), Fixed(-2), Fixed(2), Fixed(2))
        self.gen = self.Move()

    def Process(self):
        self.gen.__next__()
        Enemy.Process(self)

    def Move(self):
        cnt = 0
        smoke_cnt = 0
        while True:
            cnt += 1
            if cnt < 90:
                target_angle = self.Search(Shooting.scene.player)
                diff_angle = target_angle - self.angle
                if diff_angle > math.pi:
                    diff_angle -= 2 * math.pi
                if diff_angle < -math.pi:
                    diff_angle += 2 * math.pi
                self.angle += diff_angle * 0.1
                if self.angle > math.pi:
                    self.angle -= 2 * math.pi
                if self.angle < math.pi:
                    self.angle += 2 * math.pi
            cos_val = math.cos(self.angle)
            sin_val = math.sin(self.angle)
            self.velocity_x = int((self.velocity_x + Fixed(cos_val * 0.6)) * 0.97)
            self.velocity_y = int((self.velocity_y + Fixed(sin_val * 0.6)) * 0.97)
            self.x += self.velocity_x
            self.y += self.velocity_y
            angle = self.angle + (2 * math.pi / 32.0)
            frame = int((angle * 16) / (2 * math.pi))
            while frame > 15:
                frame -= 16
            while frame < 0:
                frame += 16
            self.sprite.SetFrame(frame)
            smoke_cnt += 1
            smoke_cnt &= 1
            if smoke_cnt == 0:
                Shooting.scene.explosions.Append(Smoke(self.x + Fixed(cos_val * -10), self.y + Fixed(sin_val * -10), Fixed(cos_val * -5) + Fixed(effect_rand.randrange(256) - 128) / 256, Fixed(sin_val * -5) + Fixed(effect_rand.randrange(256) - 128) / 256))
            yield None


class Bullet(Actor):
    def __init__(self, x, y, velocity_x, velocity_y):
        Actor.__init__(self)
        self.x = x
        self.y = y
        self.velocity_x = velocity_x
        self.velocity_y = velocity_y
        self.cnt = 0
        self.sprite = Sprite(Gss.data.bullet_surface, -7, -7, 16, 16)
        self.collision = PointCollision(Fixed(-16), Fixed(-16), Fixed(16), Fixed(16))

    def Process(self):
        self.x += self.velocity_x
        self.y += self.velocity_y
        self.cnt += 1
        self.cnt &= 1
        self.sprite.SetFrame(self.cnt)
        if self.CheckSceneOut() == True:
            Shooting.scene.bullets.Remove(self)

    def FromAngle(cls, x, y, angle, speed):
        return Bullet(x, y, Fixed(math.cos(angle) * speed), Fixed(math.sin(angle) * speed))
    FromAngle = classmethod(FromAngle)

    def FromAngle3Way(cls, x, y, angle, angle2, speed):
        return (Bullet(x, y, Fixed(math.cos(angle) * speed), Fixed(math.sin(angle) * speed)),
                Bullet(x, y, Fixed(math.cos(angle + angle2) * speed), Fixed(math.sin(angle + angle2) * speed)),
                Bullet(x, y, Fixed(math.cos(angle - angle2) * speed), Fixed(math.sin(angle - angle2) * speed)))
    FromAngle3Way = classmethod(FromAngle3Way)

    def FromAngleSpread(cls, x, y, angle, speed, power, num):
        bullets = []
        for i in range(num):
            offset_vector = RandomEnemyVector(enemy_rand.randrange(Fixed(power)))
            velocity_x = Fixed(math.cos(angle) * speed) + offset_vector[0]
            velocity_y = Fixed(math.sin(angle) * speed) + offset_vector[1]
            bullets.append(Bullet(x, y, velocity_x, velocity_y))
        return bullets
    FromAngleSpread = classmethod(FromAngleSpread)


class LongBullet(Bullet):
    def __init__(self, x, y, velocity_x, velocity_y):
        Bullet.__init__(self, x, y, velocity_x, velocity_y)
        self.sprite = Sprite(Gss.data.longbullet_surface, -24, -16, 48, 32)
        self.collision = Collision(Fixed(-24), Fixed(-16), Fixed(48), Fixed(32))


class Explosion(Actor):
    def __init__(self, x, y, velocity_x, velocity_y):
        Actor.__init__(self)
        self.x = x
        self.y = y
        self.sprite = Sprite(Gss.data.explosion_surface, -16, -16, 32, 32)
        self.collision = Collision(Fixed(-16), Fixed(-16), Fixed(16), Fixed(16))
        self.velocity_x = velocity_x
        self.velocity_y = velocity_y
        self.cnt = 0

    def Process(self):
        self.x += self.velocity_x
        self.y += self.velocity_y
        self.cnt += 1
        self.sprite.SetFrame(self.cnt // 2)
        if self.cnt >= 32 or self.CheckSceneOut() == True:
            Shooting.scene.explosions.Remove(self)


class Smoke(Explosion):
    def __init__(self, x, y, velocity_x, velocity_y):
        Actor.__init__(self)
        self.x = x
        self.y = y
        self.sprite = Sprite(Gss.data.smoke_surface, -16, -16, 32, 32)
        self.collision = Collision(Fixed(-16), Fixed(-16), Fixed(16), Fixed(16))
        self.velocity_x = velocity_x
        self.velocity_y = velocity_y
        self.cnt = 0


class BigExplosion(Explosion):
    def __init__(self, x, y, velocity_x, velocity_y):
        Actor.__init__(self)
        self.x = x
        self.y = y
        self.sprite = Sprite(Gss.data.bigexplosion_surface, -64, -64, 128, 128)
        self.collision = Collision(Fixed(-64), Fixed(-64), Fixed(64), Fixed(64))
        self.velocity_x = velocity_x
        self.velocity_y = velocity_y
        self.cnt = 0


class PlayerExplosion(Explosion):
    def __init__(self, x, y, velocity_x, velocity_y):
        Actor.__init__(self)
        self.x = x
        self.y = y
        self.sprite = Sprite(Gss.data.playerexplosion_surface, -16, -16, 32, 32)
        self.collision = Collision(Fixed(-16), Fixed(-16), Fixed(16), Fixed(16))
        self.velocity_x = velocity_x
        self.velocity_y = velocity_y
        self.cnt = 0


class BulletExplosion(Explosion):
    def __init__(self, x, y, velocity_x, velocity_y):
        Actor.__init__(self)
        self.x = x
        self.y = y
        self.sprite = Sprite(Gss.data.bulletexplosion_surface, -16, -16, 32, 32)
        self.collision = Collision(Fixed(-16), Fixed(-16), Fixed(16), Fixed(16))
        self.velocity_x = velocity_x
        self.velocity_y = velocity_y
        self.cnt = 0


class Star(Actor):
    def __init__(self):
        Actor.__init__(self)
        self.x = Fixed(effect_rand.randrange(SCREEN_WIDTH))
        self.y = Fixed(effect_rand.randrange(SCREEN_HEIGHT))
        self.sprite = Sprite(Gss.data.star_surface, -32, -8, 64, 16)
        self.collision = Collision(Fixed(-32), Fixed(-8), Fixed(32), Fixed(8))
        self.velocity_x = 0
        self.velocity_y = 0
        self.speed = effect_rand.randrange(255) + 16

    def Process(self):
        self.velocity_x = self.speed * Shooting.scene.status.GetEventSpeed() / -16
        self.x += self.velocity_x
        self.y += self.velocity_y
        if self.CheckSceneOut() == True:
            self.x = Fixed(SCREEN_WIDTH + 32)
            self.y = Fixed(effect_rand.randrange(SCREEN_HEIGHT))
            self.speed = effect_rand.randrange(255) + 16


class Ending:
    def __init__(self):
        self.typewriterstring = None
        self.gen = self.Move()

    def Process(self):
        if self.typewriterstring != None:
            self.typewriterstring.Process()
        return self.gen.__next__()

    def Draw(self, screen_surface):
        if self.typewriterstring != None:
            self.typewriterstring.Draw(screen_surface)

    def Move(self):
        self.typewriterstring = TypewriterString(176, 180, "MISSION COMPLETED!")
        for i in range(180):
            yield self
        self.typewriterstring = TypewriterString(272, 180, "BUT...")
        for i in range(180):
            yield self
        Shooting.scene.player.Suicide()
        yield None


class FloatString:
    def __init__(self, x, y, string):
        self.x = x - Fixed(8)
        self.y = y - Fixed(8)
        self.string = string
        self.scale = Fixed(0)
        self.len = len(self.string)
        self.gen = self.Move()

    def Process(self):
        return self.gen.__next__()

    def Draw(self, screen_surface):
        x = self.x - self.scale * self.len / 2
        for character in self.string:
            Gss.data.font.Draw(character, screen_surface, ScreenInt(x), ScreenInt(self.y))
            x += self.scale

    def Move(self):
        for i in range(16):
            self.scale = Fixed(i)
            self.y -= Fixed(2)
            yield self
        for i in range(60):
            self.y -= Fixed(0.5)
            yield self
        for i in range(16):
            self.scale = Fixed(15 - i)
            self.y -= Fixed(2)
            yield self
        yield None


class TypewriterString:
    def __init__(self, x, y, string):
        self.x = x
        self.y = y
        self.string = string
        self.len = len(string)
        self.num_draw = 0
        self.cursor_exists = True
        self.gen = self.Move()

    def Process(self):
        return self.gen.__next__()

    def Draw(self, screen_surface):
        x = self.x
        for i in range(self.num_draw):
            character = self.string[i]
            Gss.data.font.Draw(character, screen_surface, x, self.y)
            x += 16
        if self.cursor_exists == True:
            Gss.data.font.Draw("+", screen_surface, x, self.y)

    def Move(self):
        for i in range(self.len):
            self.num_draw += 1
            yield False
        for i in range(7):
            for j in range(2):
                self.cursor_exists = False
                yield True
                self.cursor_exists = True
                for k in range(7 - i):
                    yield True
        self.cursor_exists = False
        while True:
            yield True


class GameOverString:
    STATE_APPEAR = 0
    STATE_APPEARED = 1
    STATE_DISAPPEAR = 2
    STATE_DISAPPEARED = 3

    def __init__(self):
        self.angle = 120
        self.scale = 120
        self.gen = self.Appear()
        self.state = GameOverString.STATE_APPEAR

    def Process(self):
        return self.gen.__next__()

    def Draw(self, screen_surface):
        for i in range(9):
            cos_val = math.cos(self.angle)
            sin_val = math.sin(self.angle)
            x = int((((i - 4) * 32) * self.scale * cos_val) / 15 - 16 + 320)
            y = int((((i - 4) * 32) * self.scale * sin_val) / 15 - 16 + 240)
            rect = (i * 32, 0, 32, 32)
            screen_surface.blit(Gss.data.gameoverstring_surface, (x, y), rect)

    def GetState(self):
        return self.state

    def ToDisappear(self):
        self.gen = self.Disappear()
        self.state = GameOverString.STATE_DISAPPEAR

    def Appear(self):
        for i in range(60):
            self.angle = (i - 59) / 5.0
            self.scale = 59 - i + 15
            yield self
        self.state = GameOverString.STATE_APPEARED
        while True:
            yield self

    def Disappear(self):
        for i in range(30):
            self.scale = i * 5 + 15
            yield self
        self.state = GameOverString.STATE_DISAPPEARED
        while True:
            yield self


class TypewriterText:
    def __init__(self, strings):
        self.strings = strings
        self.len = len(self.strings)
        self.num_draw = 0
        self.gen = self.Move()

    def Process(self):
        return self.gen.__next__()

    def Draw(self, screen_surface):
        for i in range(self.num_draw + 1):
            self.strings[i].Draw(screen_surface)

    def Move(self):
        while True:
            if self.strings[self.num_draw].Process() == True:
                if self.num_draw < (self.len - 1):
                    self.num_draw += 1
            yield None


class ActorList:
    def __init__(self, num_actor):
        self.num_actor = num_actor
        self.actors = [None] * num_actor

    def __iter__(self):
        for actor in self.actors:
            if actor != None:
                yield actor

    def Append(self, actor):
        for i in range(self.num_actor):
            if self.actors[i] == None:
                self.actors[i] = actor
                return True
        return False

    def Remove(self, actor):
        for i in range(self.num_actor):
            if self.actors[i] is actor:
                self.actors[i] = None
                return True
        return False

    def GetExistingNum(self):
        num_existing = 0
        for i in range(self.num_actor):
            if self.actors[i] != None:
                num_existing += 1
        return num_existing


class Font:
    def __init__(self):
        surface = pygame.image.load("font.bmp")
        surface.set_colorkey(0)
        self.surface = surface.convert()

    def Draw(self, character, screen_surface, x, y):
        code = ord(character)
        screen_surface.blit(self.surface, (x, y), ((code & 15) * 16, (code // 16) * 16, 16, 16))

    def DrawString(self, string, screen_surface, x, y):
        for character in string:
            code = ord(character)
            screen_surface.blit(self.surface, (x, y), ((code & 15) * 16, (code // 16) * 16, 16, 16))
            x += 16


class Data:
    def __init__(self):
        self.player_surface = pygame.image.load("player.bmp").convert()
        self.enemy_surface = pygame.image.load("enemy.bmp").convert()
        self.middleenemy_surface = pygame.image.load("middleenemy.bmp").convert()
        self.bossenemy_surface = pygame.image.load("bossenemy.bmp").convert()
        self.missile_surface = pygame.image.load("missile.bmp")
        self.missile_surface.set_colorkey(0)
        self.missile_surface = self.missile_surface.convert()
        self.bullet_surface = pygame.image.load("bullet.bmp")
        self.bullet_surface.set_colorkey(0)
        self.bullet_surface = self.bullet_surface.convert()
        self.longbullet_surface = pygame.image.load("longbullet.bmp").convert()
        self.explosion_surface = pygame.image.load("explosion.bmp")
        self.explosion_surface.set_colorkey(0)
        self.explosion_surface = self.explosion_surface.convert()
        self.bigexplosion_surface = pygame.image.load("bigexplosion.bmp")
        self.bigexplosion_surface.set_colorkey(0)
        self.bigexplosion_surface = self.bigexplosion_surface.convert()
        self.smoke_surface = pygame.image.load("smoke.bmp")
        self.smoke_surface.set_colorkey(0)
        self.smoke_surface = self.smoke_surface.convert()
        self.playerexplosion_surface = pygame.image.load("playerexplosion.bmp")
        self.playerexplosion_surface.set_colorkey(0)
        self.playerexplosion_surface = self.playerexplosion_surface.convert()
        self.bulletexplosion_surface = pygame.image.load("bulletexplosion.bmp")
        self.bulletexplosion_surface.set_colorkey(0)
        self.bulletexplosion_surface = self.bulletexplosion_surface.convert()
        self.beam_surface = pygame.image.load("beam.bmp").convert()
        self.star_surface = pygame.image.load("star.bmp")
        self.star_surface.set_colorkey(0)
        self.star_surface = self.star_surface.convert()
        self.gameoverstring_surface = pygame.image.load("gameover.bmp")
        self.gameoverstring_surface.set_colorkey(0)
        self.gameoverstring_surface = self.gameoverstring_surface.convert()
        self.font = Font()
        self.explosion_sound = pygame.mixer.Sound("explosion.wav")
        self.explosion_small_sound = pygame.mixer.Sound("explosion_small.wav")
        self.explosion_large_sound = pygame.mixer.Sound("explosion_large.wav")
        self.missile_sound = pygame.mixer.Sound("missile.wav")
        self.beam_sound = pygame.mixer.Sound("beam.wav")


class Status:
    destruction_scale = 0.0
    frame_scale = 0.0
    event_scale = 0.0

    def __init__(self):
        self.frame_num = 0
        self.begin_ticks = pygame.time.get_ticks()
        self.score = 0
        self.multiplier = 1
        self.player_stock = 3
        self.event_count = Fixed(0)
        self.event_speed = Fixed(1)
        self.frame_count = 0
        self.lap_time = 0
        self.completed = False
        self.agent_score = 0.0
        self.agent_destruction_score = 0.0
        self.agent_frame_score = 0.0
        self.agent_event_score = 0.0
        self.penalty = 1.0

    def IncrementFrameNum(self):
        self.frame_num += 1

    def UpdateMultiplier(self, live_cnt):
        if live_cnt > 30:
            self.multiplier += (live_cnt - 30) / 32

    def ResetMultilier(self):
        self.multiplier = 1

    def AddScore(self, base_score):
        self.score += base_score

    def AddSuicideScore(self):
        score = self.player_stock
        self.score += score
        return score

    def DecrementPlayerStock(self, num):
        self.player_stock -= num
        if self.player_stock < 0:
            self.player_stock = 0
        if self.player_stock == 0:
            self.SetCompleted()
        return self.player_stock

    def IncrementEventCount(self):
        previous_event_count = self.event_count
        self.event_count += self.event_speed
        self.frame_count += 1
        return ScreenInt(self.event_count) - ScreenInt(previous_event_count)

    def AddEventSpeed(self, velocity):
        self.event_speed += velocity
        if self.event_speed < Fixed(0.5):
            self.event_speed = Fixed(0.5)
        if self.event_speed > Fixed(4):
            self.event_speed = Fixed(4)

    def GetEventSpeed(self):
        return self.event_speed

    def IncrementLapTime(self):
        if self.completed == False:
            self.lap_time += 1

    def GetLapTime(self):
        return self.lap_time

    def SetCompleted(self):
        self.completed = True
        self.agent_destruction_score = float(self.score)
        self.agent_frame_score = float(self.frame_count)
        self.agent_event_score = float(ScreenInt(self.event_count))
        self.agent_score = (self.agent_destruction_score * Status.destruction_scale + self.agent_frame_score * Status.frame_scale + self.agent_event_score * Status.event_scale + agent_rand.random()) * self.penalty

    def GetCompleted(self):
        return self.completed

    def UpdatePenalty(self, penalty):
        if self.penalty > penalty:
            self.penalty = penalty

    def UpdateScales(cls):
        Status.destruction_scale = agent_rand.random()
        Status.frame_scale = agent_rand.random()
        Status.event_scale = agent_rand.random()
    UpdateScales = classmethod(UpdateScales)

    def Draw(self, screen_surface):
        lap_time_min = self.lap_time / (60 * 60)
        lap_time_sec = (self.lap_time / 60) % 60
        lap_time_under_sec = (self.lap_time % 60) * 100 / 60 + 1
        Gss.data.font.DrawString("SCORE:   %010d  SPEED:         %03d%%" % (self.score, ScreenInt(self.event_speed * 100)), screen_surface, 0, 0)
        display_player_stock = self.player_stock - 1
        if display_player_stock < 0:
            display_player_stock = 0
        ticks = pygame.time.get_ticks() - self.begin_ticks
        if ticks > 0:
            fps = (self.frame_num * 1000) / ticks
        else:
            fps = 99
        Gss.data.font.DrawString("PLAYER STOCK:     %1d  FRAME RATE:     %03d" % (display_player_stock, fps), screen_surface, 0, 16)


class Scene:
    BEAM_NUM = 5
    ENEMY_NUM = 64
    BULLET_NUM = 128
    EXPLOSION_NUM = 128
    STAR_NUM = 32

    def __init__(self):
        self.player = Player()
        self.beams = ActorList(Scene.BEAM_NUM)
        self.enemies = ActorList(Scene.ENEMY_NUM)
        self.bullets = ActorList(Scene.BULLET_NUM)
        self.explosions = ActorList(Scene.EXPLOSION_NUM)
        self.stars = ActorList(Scene.STAR_NUM)
        for i in range(Scene.STAR_NUM):
            self.stars.Append(Star())
        self.floatstring = None
        self.gameoverstring = None
        self.ending = None
        self.status = Status()

    def CheckBeamEnemyCollision(self):
        for beam in self.beams:
            for enemy in self.enemies:
                if enemy.HasCollision() == True and beam.CheckCollision(enemy) == True:
                    enemy.AddDamage(1)
                    self.beams.Remove(beam)
                    Gss.agents[Gss.agent_index].SetCurrentReward(1.0)
                    break

    def CheckBulletPlayerCollision(self):
        for bullet in self.bullets:
            if self.player.HasCollision() == True and bullet.CheckCollision(self.player) == True:
                self.player.AddDamage(1)
                self.bullets.Remove(bullet)
                Gss.agents[Gss.agent_index].SetCurrentReward(-1.0)

    def CheckEnemyPlayerCollision(self):
        for enemy in self.enemies:
            if self.player.HasCollision() == True and enemy.HasCollision() == True and enemy.CheckCollision(self.player) == True:
                self.player.AddDamage(1)
                enemy.AddDamage(1)
                Gss.agents[Gss.agent_index].SetCurrentReward(-1.0)


class EventParser:
    def __init__(self, events):
        self.events = events
        self.gen = self.ParseEvents()

    def Process(self):
        self.gen.__next__()

    def ParseEvents(self):
        for event in self.events:
            result = event[0](event[1])
            if type(result) == int:
                if result > 0:
                    for i in range(result):
                        yield None
            else:
                while result() == False:
                    yield None
        while True:
            yield None

    def AppendEnemy(cls, args):
        Shooting.scene.enemies.Append(args[0](*args[1]))
        return 0
    AppendEnemy = classmethod(AppendEnemy)

    def Idle(cls, frame_num):
        return frame_num
    Idle = classmethod(Idle)

    def WaitEnemyDestroyed(cls, dummy):
        return EventParser.EnemyDestroyed
    WaitEnemyDestroyed = classmethod(WaitEnemyDestroyed)

    def BeginEnding(cls, dummy):
        Shooting.scene.ending = Ending()
        Shooting.scene.status.SetCompleted()
        return 0
    BeginEnding = classmethod(BeginEnding)

    def EnemyDestroyed(cls):
        if Shooting.scene.enemies.GetExistingNum() == 0:
            return True
        else:
            return False
    EnemyDestroyed = classmethod(EnemyDestroyed)


class Joystick:
    UP = 1
    DOWN = 2
    LEFT = 4
    RIGHT = 8
    A = 16
    B = 32

    def __init__(self):
        if pygame.joystick.get_count() > 0:
            self.joystick = pygame.joystick.Joystick(0)
            self.joystick.init()
        else:
            self.joystick = None
        self.pressed = 0
        self.trigger = 0
        self.old = 0

    def Update(self):
        key_pressed = pygame.key.get_pressed()
        self.old = self.pressed
        self.pressed = 0
        if key_pressed[pygame.K_UP] == True:
            self.pressed |= Joystick.UP
        if key_pressed[pygame.K_DOWN] == True:
            self.pressed |= Joystick.DOWN
        if key_pressed[pygame.K_LEFT] == True:
            self.pressed |= Joystick.LEFT
        if key_pressed[pygame.K_RIGHT] == True:
            self.pressed |= Joystick.RIGHT
        if key_pressed[pygame.K_z] == True:
            self.pressed |= Joystick.A
        if key_pressed[pygame.K_x] == True:
            self.pressed |= Joystick.B
        if self.joystick != None:
            if self.joystick.get_axis(1) < JOYSTICK_THRESHOLD * -1:
                self.pressed |= Joystick.UP
            if self.joystick.get_axis(1) > JOYSTICK_THRESHOLD:
                self.pressed |= Joystick.DOWN
            if self.joystick.get_axis(0) < JOYSTICK_THRESHOLD * -1:
                self.pressed |= Joystick.LEFT
            if self.joystick.get_axis(0) > JOYSTICK_THRESHOLD:
                self.pressed |= Joystick.RIGHT
            if self.joystick.get_button(0) == True:
                self.pressed |= Joystick.A
            if self.joystick.get_button(1) == True:
                self.pressed |= Joystick.B
        if self.pressed & Joystick.UP and self.pressed & Joystick.DOWN:
            self.pressed &= (Joystick.LEFT | Joystick.RIGHT | Joystick.A | Joystick.B)
        if self.pressed & Joystick.LEFT and self.pressed & Joystick.RIGHT:
            self.pressed &= (Joystick.UP | Joystick.DOWN | Joystick.A | Joystick.B)
        self.trigger = (self.pressed ^ self.old) & self.pressed

    def GetPressed(self):
        return self.pressed

    def GetTrigger(self):
        return self.trigger


class NeuralNetwork(nn.Module):
    INPUT_COUNT = 28
    OUTPUT_COUNT = 9
    INTERMEDIATE_COUNT = 72
    INTERMEDIATE_LAYER_COUNT = 8

    instance = None
    previous = None

    def __init__(self):
        super().__init__()
        self.input_layer = nn.Linear(NeuralNetwork.INPUT_COUNT, NeuralNetwork.INTERMEDIATE_COUNT)
        nn.init.kaiming_uniform_(self.input_layer.weight, mode="fan_in", nonlinearity="relu")
        self.intermediate_layers = []
        for i in range(NeuralNetwork.INTERMEDIATE_LAYER_COUNT):
            layer = nn.Linear(NeuralNetwork.INTERMEDIATE_COUNT, NeuralNetwork.INTERMEDIATE_COUNT)
            nn.init.kaiming_uniform_(layer.weight, mode="fan_in", nonlinearity="relu")
            self.intermediate_layers.append(layer)
        self.output_layer = nn.Linear(NeuralNetwork.INTERMEDIATE_COUNT, NeuralNetwork.OUTPUT_COUNT)
        nn.init.kaiming_uniform_(self.output_layer.weight, mode="fan_in", nonlinearity="relu")
        self.score = 0

    def forward(self, x):
        x = F.leaky_relu(self.input_layer(x))
        for layer in self.intermediate_layers:
            x = F.leaky_relu(layer(x))
        x = self.output_layer(x)
        return x

    def Load(self, genes):
        # TODO: Remove this
        pass

    def Infer(self, values):
        results = self(torch.tensor(values)).tolist()
        # print("results:", results);
        return results

    def Cross(self, neural_network, mutation_rate):
        NeuralNetwork.CrossModule(self.linear1, neural_network.linear1, mutation_rate)
        NeuralNetwork.CrossModule(self.linear2, neural_network.linear2, mutation_rate)
        NeuralNetwork.CrossModule(self.linear3, neural_network.linear3, mutation_rate)
        NeuralNetwork.CrossModule(self.linear4, neural_network.linear4, mutation_rate)
        NeuralNetwork.CrossModule(self.linear5, neural_network.linear5, mutation_rate)
        NeuralNetwork.CrossModule(self.linear6, neural_network.linear5, mutation_rate)

    def Clone(self):
        neural_network = NeuralNetwork()

        print("babu-", neural_network.linear1.weight[0, 0])

        NeuralNetwork.CopyModule(neural_network.linear1, self.linear1)
        NeuralNetwork.CopyModule(neural_network.linear2, self.linear2)
        NeuralNetwork.CopyModule(neural_network.linear3, self.linear3)
        NeuralNetwork.CopyModule(neural_network.linear4, self.linear4)
        NeuralNetwork.CopyModule(neural_network.linear5, self.linear5)
        NeuralNetwork.CopyModule(neural_network.linear6, self.linear5)

        print("ogya---", neural_network.linear1.weight[0, 0])

        return neural_network

    def GetScore(self):
        return self.score

    def SetScore(self, score):
        self.score = score

    def GetPrevious(cls):
        return NeuralNetwork.previous
    GetPrevious = classmethod(GetPrevious)

    def UpdatePrevious(cls, neural_network):
        NeuralNetwork.previous = copy.deepcopy(neural_network)
    UpdatePrevious = classmethod(UpdatePrevious)

    def CrossModule(cls, a_module, b_module, mutation_rate):
        a_data = a_module.weight.data
        b_data = b_module.weight.data
        size = a_data.size()
        row_count = size[0]
        column_count = size[1]
        for i in range(row_count):
            for j in range(column_count):
                if agent_rand.random() < mutation_rate:
                    a_data[i, j] = agent_rand.random() * 2.0 - 1.0
                    b_data[i, j] = agent_rand.random() * 2.0 - 1.0
                elif agent_rand.randrange(2) == 1:
                    value = float(a_data[i, j])
                    a_data[i, j] = float(b_data[i, j])
                    b_data[i, j] = value
    CrossModule = classmethod(CrossModule)

    def CopyModule(cls, a_module, b_module):
        a_data = a_module.weight.data
        b_data = b_module.weight.data
        size = a_data.size()
        row_count = size[0]
        column_count = size[1]
        for i in range(row_count):
            for j in range(column_count):
                a_data[i, j] = float(b_data[i, j])
    CopyModule = classmethod(CopyModule)

class Trainer:
    def __init__(self, model, lr, gamma):
        self.lr = lr
        self.gamma = gamma
        self.model = model
        self.optimizer = optim.SGD(model.parameters(), lr=self.lr)
        self.criterion = nn.SmoothL1Loss()
        self.losses = []

    def Train(self, state, action, reward, next_state):
        state = torch.tensor(state, dtype=torch.float)
        next_state = torch.tensor(next_state, dtype=torch.float)
        # if len(state.shape) == 1:
        #     state = torch.unsqueeze(state, 0)
        #     next_state = torch.unsqueeze(next_state, 0)

        # Predict next maximum Q value
        pred = self.model(next_state).tolist()
        # print("pred: ", pred)

        q_values = pred
        next_max_q_value = max(q_values)
        next_min_q_value = min(q_values)
        next_q_value = next_max_q_value
        if next_q_value < abs(next_min_q_value):
            next_q_value = next_min_q_value
        # Update the network
        self.optimizer.zero_grad()
        output = self.model(state)
        q_value = reward + self.gamma * next_q_value
        target = []
        for i in range(9):
            if i == action:
                target.append(q_value)
            else:
                target.append(output[i])
        target = torch.tensor(target, dtype=torch.float)
        # target = torch.unsqueeze(target, 0)
        loss = self.criterion(output, target)
        self.losses.append(float(loss))
        loss.backward()
        self.optimizer.step()

    def GetLosses(self):
        return self.losses

    def ClearLosses(self):
        self.losses = []


class EmulatedJoystick(Joystick):
    THRESHOLD = 0.5

    def __init__(self, shooting, agent):
        super().__init__()
        self.position = -1
        self.shooting = shooting
        self.agent = agent
        self.neural_network = agent.GetNeuralNetwork()
        self.rand = random.Random()
        self.rand.seed(agent.GetEpsilonSeed())
        self.epsilon = agent.GetEpsilon()
        self.state_values = []
        self.q_values = []
        self.action_value = 0
        self.total_max_defence_q_value = 0.0

    def Update(self):
        self.position += 1
        self.old = self.pressed
        player = self.shooting.scene.player
        bullets = self.shooting.scene.bullets
        enemies = self.shooting.scene.enemies
        explosions = self.shooting.scene.explosions
        values = [0.0] * NeuralNetwork.INPUT_COUNT
        for bullet in bullets:
            delta = ((bullet.x - player.x) / 16384.0, (bullet.y - player.y) / 16384.0)
            distance = math.sqrt(delta[0] * delta[0] + delta[1] * delta[1])
            angle = math.atan2(delta[1], delta[0]) / (2.0 * math.pi) * 360.0 + 22.5
            index = int(angle / 45.0) % 8
            value = 0.0
            if distance < 100.0:
                value = (100.0 - distance) / 100.0
            if values[index] < value:
                values[index] = value
        for enemy in enemies:
            delta = ((enemy.x - player.x) / 16384.0, (enemy.y - player.y) / 16384.0)
            distance = math.sqrt(delta[0] * delta[0] + delta[1] * delta[1])
            angle = math.atan2(delta[1], delta[0]) / (2.0 * math.pi) * 360.0 + 22.5
            index = int(angle / 45.0) % 8
            value = 0.0
            if distance < 100.0:
                value = (100.0 - distance) / 100.0
            if values[index] < value:
                values[index] = value
            if angle < 0.0:
                index = int(angle / -15.0)
                value = distance / 100.0
                if value > 1.0:
                    value = 1.0
                if index < 4 and values[index + 8] < value:
                    values[index + 8] = value
            else:
                index = int(angle / 15.0)
                value = distance / 100.0
                if value > 1.0:
                    value = 1.0
                if index < 4 and values[index + 12] < value:
                    values[index + 12] = value
        for explosion in explosions:
            if type(explosion) == BulletExplosion:
                delta = ((explosion.x - player.x) / 16384.0, (explosion.y - player.y) / 16384.0)
                distance = math.sqrt(delta[0] * delta[0] + delta[1] * delta[1])
                angle = math.atan2(delta[1], delta[0]) / (2.0 * math.pi) * 360.0 + 22.5
                if angle < 0.0:
                    index = int(angle / -15.0)
                    value = distance / 100.0
                    if value > 1.0:
                        value = 1.0
                    if index < 4 and values[index + 16] < value:
                        values[index + 16] = value
                else:
                    index = int(angle / 15.0)
                    value = distance / 100.0
                    if value > 1.0:
                        value = 1.0
                    if index < 4 and values[index + 20] < value:
                        values[index + 20] = value
        x = player.x / 16384.0
        y = player.y / 16384.0
        value = 0.0
        if x < 100.0:
            value = (100.0 - x) / 100.0
        values[24] = value
        value = 0.0
        if x > ((SCREEN_WIDTH / 2) - 100.0):
            value = (x - ((SCREEN_WIDTH / 2) - 100.0)) / 100.0
            if value > 1.0:
                value = 1.0
        values[25] = value
        value = 0.0
        if y < 100.0:
            value = (100.0 - y) / 100.0
        values[26] = value
        value = 0.0
        if y > (SCREEN_HEIGHT - 100.0):
            value = (y - (SCREEN_HEIGHT - 100.0)) / 100.0
        values[27] = value
        inferred = self.neural_network.Infer(values)
        # TODO: Remove below
        self.q_values = inferred
        q_values = inferred
        max_q_value = max(q_values)
        index = q_values.index(max_q_value)
        if self.rand.random() < self.epsilon:
            index = self.rand.randrange(9)

        self.pressed = 0
        if index == 1:
            self.pressed |= Joystick.UP
        elif index == 2:
            self.pressed |= Joystick.UP | Joystick.RIGHT
        elif index == 3:
            self.pressed |= Joystick.RIGHT
        elif index == 4:
            self.pressed |= Joystick.DOWN | Joystick.RIGHT
        elif index == 5:
            self.pressed |= Joystick.DOWN
        elif index == 6:
            self.pressed |= Joystick.DOWN | Joystick.LEFT
        elif index == 7:
            self.pressed |= Joystick.LEFT
        elif index == 8:
            self.pressed |= Joystick.UP | Joystick.LEFT
        self.pressed |= Joystick.A
        self.trigger = (self.pressed ^ self.old) & self.pressed
        self.state_values = values
        self.action_value = index

    def GetPressed(self):
        return self.pressed

    def GetTrigger(self):
        return self.trigger

    def GetStateValues(self):
        return self.state_values

    def GetQValues(self):
        return self.q_values

    def GetActionValue(self):
        return self.action_value


class Agent:
    ALPHA = 0.2
    MUTATION_RATE = 0.0 * 0.01

    def __init__(self, neural_network=None):
        if neural_network == None:
            self.neural_network = NeuralNetwork()
        else:
            self.neural_network = neural_network
        self.epsilon = 0.0
        self.epsilon_seed = agent_rand.randrange(65535)
        self.score = 0
        self.destruction_score = 0
        self.frame_score = 0
        self.event_score = 0
        self.experiences = []
        self.trainer = Trainer(self.neural_network, 0.001, 0.95)
        self.current_reward = 0.0

    def Clone(self):
        agent = Agent(copy.deepcopy(self.neural_network))
        agent.epsilon_seed = self.epsilon_seed
        agent.score = self.score
        agent.destruction_score = self.destruction_score
        agent.frame_score = self.frame_score
        agent.event_score = self.event_score
        agent.experiences = self.experiences[:]
        return agent

    def Remember(self, experience):
        self.experiences.append(experience)

    def Train(self):
        self.TrainLongMemory()
        average_loss = self.GetAverageLoss()
        print("Average loss: {:.5f}".format(average_loss))

    def TrainShortMemory(self):
        # TODO: Remove this
        loop_count = len(self.experiences) - 1
        for i in range(loop_count):
            experience = self.experiences[i]
            next_experience = self.experiences[i + 1]
            self.trainer.Train(experience[0], experience[1], experience[2], next_experience[0])
        self.experiences = []

    def TrainLongMemory(self):
        self.neural_network.SetScore(self.score)
        # previous_neural_network = NeuralNetwork.GetPrevious()
        # print("Current score: ", self.score)
        # if previous_neural_network != None:
        #     print("Previous score: ", previous_neural_network.GetScore())
        if False: # previous_neural_network != None and self.score < previous_neural_network.GetScore():
            pass
        #     print("Neural network rollbacked.")
        #     self.neural_network = copy.deepcopy(NeuralNetwork.GetPrevious())
        else:
            # NeuralNetwork.UpdatePrevious(self.neural_network)
            # TODO: Serialize the neural network
            loop_count = len(self.experiences) - 1
            a_indices = []
            for i in range(loop_count):
                a_indices.append(i)
            indices = []
            for i in range(loop_count):
                index = a_indices[agent_rand.randrange(len(a_indices))]
                a_indices.remove(index)
                indices.append(index)
            for i in indices:
                experience = self.experiences[i]
                # print("babu-", experience[3])
                next_experience = self.experiences[i + 1]
                self.trainer.Train(experience[0], experience[1], experience[2], next_experience[0])
        self.experiences = []

    def ClearExperiences(self):
        self.experiences = []

    def SetCurrentReward(self, reward):
        self.current_reward = reward

    def GetCurrentReward(self):
        return self.current_reward

    def ClearCurrentRewards(self):
        self.current_reward = 0.0

    def Cross(self, agent):
        self.neural_network.Cross(agent.neural_network, Agent.MUTATION_RATE)

    def CrossWithBCXAlpha(self, agent):
        for i in range(len(self.genes)):
            if agent_rand.random() <= Agent.MUTATION_RATE * 0.01:
                self.genes[i] = agent_rand.random() * 2.0 - 1.0
                agent.genes[i] = agent_rand.random() * 2.0 - 1.0
            else:
                min_value = min(self.genes[i], agent.genes[i])
                max_value = max(self.genes[i], agent.genes[i])
                diff = max_value - min_value
                min_value -= diff * Agent.ALPHA
                diff += diff * Agent.ALPHA * 2.0
                ratio = agent_rand.random()
                self.genes[i] = min_value + diff * ratio
                agent.genes[i] = min_value + diff * (1.0 - ratio)

    def GetGenes(self):
        return self.genes

    def GetScore(self):
        return self.score

    def SetScore(self, score):
        self.score = score

    def GetDestructionScore(self):
        return self.destruction_score

    def SetDestructionScore(self, destruction_score):
        self.destruction_score = destruction_score

    def GetFrameScore(self):
        return self.frame_score

    def SetFrameScore(self, frame_score):
        self.frame_score = frame_score

    def GetEventScore(self):
        return self.event_score

    def SetEventScore(self, event_score):
        self.event_score = event_score

    def GetNeuralNetwork(self):
        return self.neural_network

    def GetEpsilon(self):
        return self.epsilon

    def SetEpsilon(self, epsilon):
        self.epsilon = epsilon

    def GetEpsilonSeed(self):
        return self.epsilon_seed

    def UpdateEpsilonSeed(self):
        self.epsilon_seed = agent_rand.randrange(65535)

    def GetAverageLoss(self):
        losses = self.trainer.GetLosses()
        total = 0.0
        for loss in losses:
            total += loss
        average = total / len(losses)
        self.trainer.ClearLosses()
        return average

    def GetAlternated(cls, agents):
        elite = None
        scores = []
        for agent in agents:
            score = agent.GetScore()
            scores.append(score)
        sorted_scores = sorted(scores, reverse=True)
        new_agents = []
        if sorted_scores[0] > agents[0].GetScore():
            elite = Agent.GetFromScore(agents, sorted_scores[0]).Clone()
            new_agents.append(elite)
        else:
            elite = agents[0]
            new_agents.append(elite)
        for i in range(len(agents) - 1):
            agent = agents[i + 1]
            agent.UpdateEpsilonSeed()
            new_agents.append(agent)
        return new_agents
    GetAlternated = classmethod(GetAlternated)

    def Load(cls, filename):
        with open(filename, "rb") as file:
            saved = pickle.load(file)
        return saved["agents"], saved["generation"]
    Load = classmethod(Load)

    def Save(cls, agents, generation, filename):
        saving = {"generation": generation, "agents": agents}
        with open(filename, "wb") as file:
            pickle.dump(saving, file)
    Save = classmethod(Save)

    def GetFromScore(cls, agents, score):
        for agent in agents:
            if agent.GetScore() == score:
                return agent
        return None
    GetFromScore = classmethod(GetFromScore)


class Gss:
    AGENT_NUM = 2

    screen_surface = None
    joystick = None
    data = None
    settings = None
    agents = []
    agent_index = 0
    best_lap_time = 59 * 60 * 60 + 59 * 60 + 59

    def __init__(self, agents, generation, settings):
        pygame.init()
        Gss.screen_surface = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.HWSURFACE | pygame.DOUBLEBUF)  # | pygame.FULLSCREEN)
        pygame.mouse.set_visible(1)
        pygame.mixer.init()
        pygame.joystick.init()
        Gss.joystick = Joystick()
        Gss.data = Data()
        Gss.settings = settings
        if agents == None:
            self.generation = 1
            for i in range(Gss.AGENT_NUM):
                Gss.agents.append(Agent())
        else:
            self.generation = generation
            for agent in agents:
                Gss.agents.append(agent)
        Gss.agent_index = 0

    def Main(self):
        Status.UpdateScales()
        while True:
            if Title().MainLoop() == Title.STATE_EXIT_QUIT:
                return
            agent = Gss.agents[Gss.agent_index]
            if Gss.agent_index > 0:
                # Run shooting for training
                enemy_rand.seed(agent_rand.randrange(65536))
                effect_rand.seed(agent_rand.randrange(65536))
                agent.SetEpsilon(0.1)
                agent.UpdateEpsilonSeed()
                shooting = Shooting()
                Gss.joystick = EmulatedJoystick(shooting, agent)
                shooting.MainLoop()
                agent.Train()
                agent.ClearExperiences()
            if not Gss.settings.GetEliteSkipping() or Gss.agent_index > 0:
                # Run shooting for scoring
                enemy_rand.seed(123)
                effect_rand.seed(456)
                agent.SetEpsilon(0.0)
                shooting = Shooting()
                Gss.joystick = EmulatedJoystick(shooting, agent)
                shooting.MainLoop()
                agent.ClearExperiences()
                score = shooting.scene.status.agent_score
                agent.SetScore(score)
                destruction_score = shooting.scene.status.agent_destruction_score
                agent.SetDestructionScore(destruction_score)
                frame_score = shooting.scene.status.agent_frame_score
                agent.SetFrameScore(frame_score)
                event_score = shooting.scene.status.agent_event_score
                agent.SetEventScore(event_score)
            print("Generation: {}, Agent: {}, Score: {:.1f}, Destruction score: {:.1f}, Frame score: {:.1f}, Event score: {:.1f}".format(self.generation, self.agent_index, agent.GetScore(), agent.GetDestructionScore(), agent.GetFrameScore(), agent.GetEventScore()))
            Gss.joystick = Joystick()
            Gss.agent_index += 1
            if Gss.agent_index >= Gss.AGENT_NUM:
                Gss.agents = Agent.GetAlternated(Gss.agents)
                Gss.agent_index = 0
                self.generation += 1
                Agent.Save(Gss.agents, self.generation, "gen{}.pickle".format(self.generation))


class LogoPart(Actor):
    def __init__(self, x, y):
        Actor.__init__(self)
        self.x = x
        self.y = y
        offset_x = x - Fixed(320)
        offset_y = y - Fixed(168)
        self.offset_x = offset_x
        self.offset_y = offset_y
        self.distance = math.sqrt(offset_x * offset_x + offset_y * offset_y)
        self.sprite = Sprite(Gss.data.enemy_surface, -16, -16, 32, 32)

    def Process(self, scale_param):
        index = int(self.distance / 65536.0) & 255
        self.x = (self.offset_x * scale_param[index]) / FIXED_MUL + Fixed(320)
        self.y = (self.offset_y * scale_param[index]) / FIXED_MUL + Fixed(168)


logo_part_positions = (
    (Fixed(160), Fixed(96)),
    (Fixed(192), Fixed(96)),
    (Fixed(224), Fixed(96)),
    (Fixed(160), Fixed(128)),
    (Fixed(160), Fixed(160)),
    (Fixed(224), Fixed(160)),
    (Fixed(160), Fixed(192)),
    (Fixed(224), Fixed(192)),
    (Fixed(160), Fixed(224)),
    (Fixed(192), Fixed(224)),
    (Fixed(224), Fixed(224)),

    (Fixed(288), Fixed(96)),
    (Fixed(320), Fixed(96)),
    (Fixed(352), Fixed(96)),
    (Fixed(288), Fixed(128)),
    (Fixed(288), Fixed(160)),
    (Fixed(320), Fixed(160)),
    (Fixed(352), Fixed(160)),
    (Fixed(352), Fixed(192)),
    (Fixed(288), Fixed(224)),
    (Fixed(320), Fixed(224)),
    (Fixed(352), Fixed(224)),

    (Fixed(416), Fixed(96)),
    (Fixed(448), Fixed(96)),
    (Fixed(480), Fixed(96)),
    (Fixed(416), Fixed(128)),
    (Fixed(416), Fixed(160)),
    (Fixed(448), Fixed(160)),
    (Fixed(480), Fixed(160)),
    (Fixed(480), Fixed(192)),
    (Fixed(416), Fixed(224)),
    (Fixed(448), Fixed(224)),
    (Fixed(480), Fixed(224)),
)


class Logo:
    def __init__(self):
        self.parts = []
        for position in logo_part_positions:
            self.parts.append(LogoPart(position[0], position[1]))
        self.scale_param = [Fixed(0.0)] * 256
        self.base_scale = 0.0
        self.wave_scale = 1.0
        self.phase = 0.0
        self.gen = self.Appear()

    def Process(self):
        self.gen.__next__()
        self.Scale()
        for part in self.parts:
            part.Process(self.scale_param)

    def Draw(self, screen_surface):
        for part in self.parts:
            part.Draw(screen_surface)

    def Scale(self):
        scale = math.sin(self.phase) * self.wave_scale + self.base_scale
        self.scale_param = [Fixed(scale)] + self.scale_param[:-1]

    def Appear(self):
        for i in range(128):
            self.base_scale = i / 127.0
            self.wave_scale = (1.0 - i / 127.0) * 2.0
            self.phase += 2.0 * math.pi / 128.0
            yield None
        while True:
            yield None

    def Disappear(self):
        for i in range(128):
            self.base_scale = 1.0 + i / 32.0
            self.wave_scale = i / 32.0
            self.phase += 2.0 * math.pi / 96.0
            yield None
        while True:
            yield None

    def ToDisappear(self):
        self.gen = self.Disappear()


class Title:
    STATE_CONTINUE = 0
    STATE_EXIT_QUIT = 1
    STATE_EXIT_START = 2

    def __init__(self):
        self.logo = Logo()
        self.typewritertext = TypewriterText((TypewriterString(216, 256, "VERSION %s" % VERSION), TypewriterString(160, 384, "(C)2005 - 2020 GONY."), TypewriterString(136, 416,
                                                                                                                                                                       "DEDICATED TO KENYA ABE."), TypewriterString(272, 48, "SHIPPU"), TypewriterString(464, 240, "NN"), TypewriterString(224, 320, "PRESS BUTTON")))
        self.gen = self.Move()

    def MainLoop(self):
        frame_count = 0
        state = Title.STATE_CONTINUE
        while state == Title.STATE_CONTINUE:
            begin_ticks = pygame.time.get_ticks()
            for event in pygame.event.get():
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        state = Title.STATE_EXIT_QUIT
                    if event.key == pygame.K_c:
                        Gss.settings.SetNoWait(not Gss.settings.GetNoWait())
                    if event.key == pygame.K_v:
                        Gss.settings.SetFrameSkipping(not Gss.settings.GetFrameSkipping())
                    if event.key == pygame.K_b:
                        Gss.settings.SetEliteSkipping(not Gss.settings.GetEliteSkipping())
            Gss.screen_surface.fill((0, 0, 0))
            Gss.joystick.Update()
            self.typewritertext.Process()
            self.logo.Process()
            if self.gen.__next__() == True:
                state = Title.STATE_EXIT_START
            if not Gss.settings.GetFrameSkipping() or frame_count == 0:
                self.logo.Draw(Gss.screen_surface)
                self.typewritertext.Draw(Gss.screen_surface)
                lap_time_min = Gss.best_lap_time / (60 * 60)
                lap_time_sec = (Gss.best_lap_time / 60) % 60
                lap_time_under_sec = (Gss.best_lap_time % 60) * 100 / 60 + 1
                Gss.data.font.DrawString("BEST LAP: %02d'%02d''%02d" % (lap_time_min, lap_time_sec, lap_time_under_sec), Gss.screen_surface, 0, 0)
                pygame.display.flip()
                ticks = pygame.time.get_ticks() - begin_ticks
                frame_time = 16
                if Gss.settings.GetNoWait():
                    frame_time = 1
                if ticks < frame_time:
                    pygame.time.delay(frame_time - ticks)
            frame_count += 1
            frame_count %= 600
        return state

    def Move(self):
        for i in range(128):
            yield False
        count = 0
        done = False
        while done == False:
            trigger = Gss.joystick.GetTrigger()
            if trigger & Joystick.A:
                self.logo.ToDisappear()
                done = True
            count += 1
            if count >= 60:
                self.logo.ToDisappear()
                done = True
            yield False
        for i in range(128):
            yield False
        while True:
            yield True


test_events = (
    (EventParser.Idle, 60),

    # イントロ
    (EventParser.AppendEnemy, (StraightEnemy, (Fixed(640), Fixed(120)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightEnemy, (Fixed(640), Fixed(80)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightEnemy, (Fixed(640), Fixed(200)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightEnemy, (Fixed(640), Fixed(16)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightEnemy, (Fixed(640), Fixed(40)))),
    (EventParser.Idle, 90),
    (EventParser.AppendEnemy, (StraightEnemy, (Fixed(640), Fixed(440)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightEnemy, (Fixed(640), Fixed(360)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightEnemy, (Fixed(640), Fixed(400)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightEnemy, (Fixed(640), Fixed(280)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightEnemy, (Fixed(640), Fixed(320)))),
    (EventParser.Idle, 90),
    (EventParser.AppendEnemy, (StraightEnemy, (Fixed(640), Fixed(120)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightEnemy, (Fixed(640), Fixed(80)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightEnemy, (Fixed(640), Fixed(200)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightEnemy, (Fixed(640), Fixed(16)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightEnemy, (Fixed(640), Fixed(40)))),
    (EventParser.Idle, 90),
    (EventParser.AppendEnemy, (StraightEnemy, (Fixed(640), Fixed(440)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightEnemy, (Fixed(640), Fixed(360)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightEnemy, (Fixed(640), Fixed(400)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightEnemy, (Fixed(640), Fixed(280)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightEnemy, (Fixed(640), Fixed(320)))),

    (EventParser.AppendEnemy, (StraightBulletEnemy, (Fixed(640), Fixed(240)))),
    (EventParser.Idle, 30),

    (EventParser.AppendEnemy, (StayEnemy, (Fixed(640), Fixed(40), Fixed(0.1)))),
    (EventParser.Idle, 30),
    (EventParser.AppendEnemy, (StayEnemy, (Fixed(640), Fixed(140), Fixed(-0.1)))),
    (EventParser.Idle, 30),
    (EventParser.AppendEnemy, (StayEnemy, (Fixed(640), Fixed(240), Fixed(0.1)))),
    (EventParser.AppendEnemy, (MiddleMissileEnemy, (Fixed(640 + 63), Fixed(350)))),
    (EventParser.Idle, 90),
    (EventParser.AppendEnemy, (StraightEnemy, (Fixed(640), Fixed(200)))),
    (EventParser.Idle, 60),
    (EventParser.AppendEnemy, (StraightEnemy, (Fixed(640), Fixed(20)))),
    (EventParser.Idle, 60),
    (EventParser.AppendEnemy, (StraightEnemy, (Fixed(640), Fixed(150)))),
    (EventParser.Idle, 60),
    (EventParser.AppendEnemy, (StraightEnemy, (Fixed(640), Fixed(0)))),
    (EventParser.Idle, 60),
    (EventParser.AppendEnemy, (StraightEnemy, (Fixed(640), Fixed(100)))),
    (EventParser.Idle, 180),

    (EventParser.AppendEnemy, (StraightBulletEnemy, (Fixed(640), Fixed(420)))),
    (EventParser.Idle, 120),
    (EventParser.AppendEnemy, (VerticalMissileEnemy, (Fixed(640), Fixed(40)))),
    (EventParser.Idle, 60),
    (EventParser.AppendEnemy, (VerticalMissileEnemy, (Fixed(640), Fixed(440)))),
    (EventParser.Idle, 60),
    (EventParser.AppendEnemy, (VerticalMissileEnemy, (Fixed(640), Fixed(40)))),
    (EventParser.Idle, 60),
    (EventParser.AppendEnemy, (VerticalMissileEnemy, (Fixed(640), Fixed(440)))),
    (EventParser.Idle, 60),
    (EventParser.AppendEnemy, (VerticalMissileEnemy, (Fixed(640), Fixed(40)))),
    (EventParser.Idle, 60),
    (EventParser.AppendEnemy, (VerticalMissileEnemy, (Fixed(640), Fixed(440)))),
    (EventParser.Idle, 60),

    (EventParser.AppendEnemy, (BackwordEnemy, (Fixed(0), Fixed(10)))),
    (EventParser.Idle, 60),
    (EventParser.AppendEnemy, (BackwordEnemy, (Fixed(0), Fixed(40)))),
    (EventParser.Idle, 60),
    (EventParser.AppendEnemy, (BackwordEnemy, (Fixed(0), Fixed(20)))),
    (EventParser.Idle, 60),

    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(360)))),
    (EventParser.Idle, 30),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(120)))),
    (EventParser.Idle, 30),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(200)))),
    (EventParser.Idle, 30),

    # 約30秒
    (EventParser.Idle, 60),

    (EventParser.AppendEnemy, (StayEnemy, (Fixed(640), Fixed(40), Fixed(0.1)))),
    (EventParser.Idle, 30),
    (EventParser.AppendEnemy, (StayEnemy, (Fixed(640), Fixed(320), Fixed(-0.1)))),
    (EventParser.Idle, 30),
    (EventParser.AppendEnemy, (StayEnemy, (Fixed(640), Fixed(240), Fixed(0.1)))),
    (EventParser.Idle, 30),
    (EventParser.AppendEnemy, (StayEnemy, (Fixed(640), Fixed(80), Fixed(0.1)))),
    (EventParser.Idle, 30),
    (EventParser.AppendEnemy, (StayEnemy, (Fixed(640), Fixed(440), Fixed(-0.1)))),
    (EventParser.Idle, 30),
    (EventParser.AppendEnemy, (StayEnemy, (Fixed(640), Fixed(160), Fixed(0.1)))),
    (EventParser.Idle, 30),
    (EventParser.AppendEnemy, (StayEnemy, (Fixed(640), Fixed(360), Fixed(-0.1)))),
    (EventParser.Idle, 30),
    (EventParser.AppendEnemy, (StayEnemy, (Fixed(640), Fixed(120), Fixed(0.1)))),
    (EventParser.Idle, 30),
    (EventParser.AppendEnemy, (MiddleEnemy, (Fixed(640 + 63), Fixed(240)))),
    (EventParser.Idle, 90),
    (EventParser.AppendEnemy, (BackwordEnemy, (Fixed(0), Fixed(10)))),
    (EventParser.Idle, 60),
    (EventParser.AppendEnemy, (BackwordEnemy, (Fixed(0), Fixed(470)))),
    (EventParser.Idle, 60),
    (EventParser.AppendEnemy, (BackwordEnemy, (Fixed(0), Fixed(10)))),
    (EventParser.Idle, 60),
    (EventParser.AppendEnemy, (BackwordEnemy, (Fixed(0), Fixed(470)))),
    (EventParser.Idle, 60),
    (EventParser.AppendEnemy, (BackwordEnemy, (Fixed(0), Fixed(10)))),
    (EventParser.Idle, 60),
    (EventParser.AppendEnemy, (BackwordEnemy, (Fixed(0), Fixed(470)))),
    (EventParser.Idle, 60),
    (EventParser.AppendEnemy, (BackwordEnemy, (Fixed(0), Fixed(10)))),
    (EventParser.Idle, 60),
    (EventParser.AppendEnemy, (BackwordEnemy, (Fixed(0), Fixed(470)))),
    (EventParser.Idle, 60),

    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(360)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(120)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(80)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(440)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(200)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(40)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(160)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(240)))),
    (EventParser.Idle, 60),

    (EventParser.AppendEnemy, (RollEnemy, (Fixed(640), Fixed(0)))),
    (EventParser.Idle, 30),
    (EventParser.AppendEnemy, (RollEnemy, (Fixed(640), Fixed(0)))),
    (EventParser.Idle, 30),
    (EventParser.AppendEnemy, (RollEnemy, (Fixed(640), Fixed(0)))),
    (EventParser.Idle, 30),
    (EventParser.AppendEnemy, (RollEnemy, (Fixed(640), Fixed(0)))),
    (EventParser.Idle, 30),
    (EventParser.AppendEnemy, (RollEnemy, (Fixed(640), Fixed(0)))),
    (EventParser.Idle, 30),
    (EventParser.AppendEnemy, (RollEnemy, (Fixed(640), Fixed(0)))),
    (EventParser.Idle, 30),
    (EventParser.AppendEnemy, (RollEnemy, (Fixed(640), Fixed(0)))),
    (EventParser.Idle, 30),
    (EventParser.AppendEnemy, (RollEnemy, (Fixed(640), Fixed(0)))),
    (EventParser.Idle, 30),
    (EventParser.AppendEnemy, (RollEnemy, (Fixed(640), Fixed(0)))),
    (EventParser.Idle, 30),
    (EventParser.AppendEnemy, (RollEnemy, (Fixed(640), Fixed(0)))),
    (EventParser.Idle, 220),
    (EventParser.AppendEnemy, (RollEnemy, (Fixed(640), Fixed(480)))),
    (EventParser.Idle, 30),
    (EventParser.AppendEnemy, (RollEnemy, (Fixed(640), Fixed(480)))),
    (EventParser.Idle, 30),
    (EventParser.AppendEnemy, (RollEnemy, (Fixed(640), Fixed(480)))),
    (EventParser.Idle, 30),
    (EventParser.AppendEnemy, (RollEnemy, (Fixed(640), Fixed(480)))),
    (EventParser.Idle, 30),
    (EventParser.AppendEnemy, (RollEnemy, (Fixed(640), Fixed(480)))),
    (EventParser.Idle, 30),
    (EventParser.AppendEnemy, (RollEnemy, (Fixed(640), Fixed(480)))),
    (EventParser.Idle, 30),
    (EventParser.AppendEnemy, (RollEnemy, (Fixed(640), Fixed(480)))),
    (EventParser.Idle, 30),
    (EventParser.AppendEnemy, (RollEnemy, (Fixed(640), Fixed(480)))),
    (EventParser.Idle, 30),
    (EventParser.AppendEnemy, (RollEnemy, (Fixed(640), Fixed(480)))),
    (EventParser.Idle, 30),
    (EventParser.AppendEnemy, (RollEnemy, (Fixed(640), Fixed(480)))),
    (EventParser.Idle, 180),

    # 約1分20秒
    (EventParser.AppendEnemy, (StraightBulletEnemy, (Fixed(640), Fixed(40)))),
    (EventParser.Idle, 10),
    (EventParser.AppendEnemy, (StraightBulletEnemy, (Fixed(640), Fixed(140)))),
    (EventParser.Idle, 10),
    (EventParser.AppendEnemy, (StraightBulletEnemy, (Fixed(640), Fixed(240)))),
    (EventParser.Idle, 10),
    (EventParser.AppendEnemy, (StraightBulletEnemy, (Fixed(640), Fixed(340)))),
    (EventParser.Idle, 10),
    (EventParser.AppendEnemy, (StraightBulletEnemy, (Fixed(640), Fixed(440)))),
    (EventParser.Idle, 10),

    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(360)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(120)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(80)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(440)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(200)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(40)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(160)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(240)))),
    (EventParser.Idle, 10),
    (EventParser.AppendEnemy, (VerticalMissileEnemy, (Fixed(640), Fixed(40)))),
    (EventParser.Idle, 30),
    (EventParser.AppendEnemy, (VerticalMissileEnemy, (Fixed(640), Fixed(440)))),
    (EventParser.Idle, 30),
    (EventParser.AppendEnemy, (VerticalMissileEnemy, (Fixed(640), Fixed(40)))),
    (EventParser.Idle, 30),
    (EventParser.AppendEnemy, (VerticalMissileEnemy, (Fixed(640), Fixed(440)))),
    (EventParser.AppendEnemy, (StraightEnemy, (Fixed(640), Fixed(120)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightEnemy, (Fixed(640), Fixed(360)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightEnemy, (Fixed(640), Fixed(240)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightEnemy, (Fixed(640), Fixed(160)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightEnemy, (Fixed(640), Fixed(320)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightEnemy, (Fixed(640), Fixed(280)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightEnemy, (Fixed(640), Fixed(200)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightEnemy, (Fixed(640), Fixed(160)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightEnemy, (Fixed(640), Fixed(120)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightEnemy, (Fixed(640), Fixed(360)))),
    (EventParser.AppendEnemy, (MiddleMissileEnemy, (Fixed(640 + 63), Fixed(120)))),
    (EventParser.Idle, 90),
    (EventParser.AppendEnemy, (StraightBulletEnemy, (Fixed(640), Fixed(240)))),
    (EventParser.Idle, 10),
    (EventParser.AppendEnemy, (StraightBulletEnemy, (Fixed(640), Fixed(340)))),
    (EventParser.Idle, 10),
    (EventParser.AppendEnemy, (StraightBulletEnemy, (Fixed(640), Fixed(440)))),
    (EventParser.Idle, 60),
    (EventParser.AppendEnemy, (StraightBulletEnemy, (Fixed(640), Fixed(240)))),
    (EventParser.Idle, 10),
    (EventParser.AppendEnemy, (StraightBulletEnemy, (Fixed(640), Fixed(340)))),
    (EventParser.Idle, 10),
    (EventParser.AppendEnemy, (StraightBulletEnemy, (Fixed(640), Fixed(440)))),
    (EventParser.Idle, 60),
    (EventParser.AppendEnemy, (StraightBulletEnemy, (Fixed(640), Fixed(240)))),
    (EventParser.Idle, 10),
    (EventParser.AppendEnemy, (StraightBulletEnemy, (Fixed(640), Fixed(340)))),
    (EventParser.Idle, 10),
    (EventParser.AppendEnemy, (StraightBulletEnemy, (Fixed(640), Fixed(440)))),
    (EventParser.Idle, 60),
    (EventParser.AppendEnemy, (MiddleMissileEnemy, (Fixed(640 + 63), Fixed(360)))),
    (EventParser.Idle, 90),
    (EventParser.AppendEnemy, (StayEnemy, (Fixed(640), Fixed(240), Fixed(0.1)))),
    (EventParser.Idle, 30),
    (EventParser.AppendEnemy, (StayEnemy, (Fixed(640), Fixed(120), Fixed(0.1)))),
    (EventParser.Idle, 30),
    (EventParser.AppendEnemy, (StayEnemy, (Fixed(640), Fixed(0), Fixed(0.1)))),
    (EventParser.Idle, 90),
    (EventParser.AppendEnemy, (StayEnemy, (Fixed(640), Fixed(240), Fixed(0.1)))),
    (EventParser.Idle, 30),
    (EventParser.AppendEnemy, (StayEnemy, (Fixed(640), Fixed(120), Fixed(0.1)))),
    (EventParser.Idle, 30),
    (EventParser.AppendEnemy, (StayEnemy, (Fixed(640), Fixed(0), Fixed(0.1)))),
    (EventParser.Idle, 90),
    (EventParser.AppendEnemy, (StayEnemy, (Fixed(640), Fixed(240), Fixed(0.1)))),
    (EventParser.Idle, 30),
    (EventParser.AppendEnemy, (StayEnemy, (Fixed(640), Fixed(120), Fixed(0.1)))),
    (EventParser.Idle, 30),
    (EventParser.AppendEnemy, (StayEnemy, (Fixed(640), Fixed(0), Fixed(0.1)))),
    (EventParser.Idle, 90),
    (EventParser.AppendEnemy, (MiddleEnemy, (Fixed(640 + 63), Fixed(120)))),
    (EventParser.Idle, 90),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(240)))),
    (EventParser.Idle, 10),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(340)))),
    (EventParser.Idle, 10),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(440)))),
    (EventParser.Idle, 60),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(240)))),
    (EventParser.Idle, 10),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(340)))),
    (EventParser.Idle, 10),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(440)))),
    (EventParser.Idle, 60),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(240)))),
    (EventParser.Idle, 10),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(340)))),
    (EventParser.Idle, 10),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(440)))),
    (EventParser.Idle, 60),
    (EventParser.AppendEnemy, (MiddleEnemy, (Fixed(640 + 63), Fixed(360)))),
    (EventParser.Idle, 90),
    (EventParser.AppendEnemy, (VerticalMissileEnemy, (Fixed(640), Fixed(40)))),
    (EventParser.Idle, 30),
    (EventParser.AppendEnemy, (VerticalMissileEnemy, (Fixed(640), Fixed(40)))),
    (EventParser.Idle, 30),
    (EventParser.AppendEnemy, (VerticalMissileEnemy, (Fixed(640), Fixed(40)))),
    (EventParser.Idle, 90),
    (EventParser.AppendEnemy, (VerticalMissileEnemy, (Fixed(640), Fixed(40)))),
    (EventParser.Idle, 30),
    (EventParser.AppendEnemy, (VerticalMissileEnemy, (Fixed(640), Fixed(40)))),
    (EventParser.Idle, 30),
    (EventParser.AppendEnemy, (VerticalMissileEnemy, (Fixed(640), Fixed(40)))),
    (EventParser.Idle, 90),
    (EventParser.AppendEnemy, (VerticalMissileEnemy, (Fixed(640), Fixed(40)))),
    (EventParser.Idle, 30),
    (EventParser.AppendEnemy, (VerticalMissileEnemy, (Fixed(640), Fixed(40)))),
    (EventParser.Idle, 30),
    (EventParser.AppendEnemy, (VerticalMissileEnemy, (Fixed(640), Fixed(40)))),
    (EventParser.Idle, 90),

    # 約1分50秒
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(360)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(120)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(80)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(440)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(200)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(40)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(160)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(240)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(25)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(170)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(340)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(420)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(240)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(460)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(70)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(410)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(90)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(200)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(60)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(210)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(120)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(20)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(50)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(110)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(230)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(470)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(380)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(190)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(430)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(270)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(470)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(440)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(290)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(420)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(360)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(230)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(330)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(140)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(410)))),
    (EventParser.Idle, 15),
    (EventParser.AppendEnemy, (StraightMissileEnemy, (Fixed(640), Fixed(170)))),
    (EventParser.Idle, 240),
    (EventParser.AppendEnemy, (BossEnemy, (Fixed(600), Fixed(768)))),
    (EventParser.WaitEnemyDestroyed, None),
    (EventParser.Idle, 60),
    (EventParser.BeginEnding, None),
)

"""
test_events = (
    (EventParser.AppendEnemy,(StraightMissileEnemy,(Fixed(640),Fixed(170)))),
    (EventParser.WaitEnemyDestroyed,None),
    (EventParser.BeginEnding,None),
)
"""


class Shooting:
    STATE_CONTINUE = 0
    STATE_EXIT_QUIT = 1
    STATE_EXIT_GAMEOVER = 2

    scene = None

    def __init__(self):
        # pygame.mixer.music.load("shippu.ogg")
        Shooting.scene = Scene()
        self.gen = self.Move()

    def MainLoop(self):
        if not Gss.settings.GetSilent():
            pass
            # pygame.mixer.music.play(-1)
        event_parser = EventParser(test_events)

        frame_count = 0
        state = Shooting.STATE_CONTINUE
        while state == Shooting.STATE_CONTINUE:
            begin_ticks = pygame.time.get_ticks()
            for event in pygame.event.get():
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        state = Shooting.STATE_EXIT_QUIT
                    if event.key == pygame.K_c:
                        Gss.settings.SetNoWait(not Gss.settings.GetNoWait())
                    if event.key == pygame.K_v:
                        Gss.settings.SetFrameSkipping(not Gss.settings.GetFrameSkipping())
                    if event.key == pygame.K_b:
                        Gss.settings.SetEliteSkipping(not Gss.settings.GetEliteSkipping())
            Gss.screen_surface.fill((0, 0, 0))
            Gss.joystick.Update()
            Shooting.scene.player.Process()
            for beam in Shooting.scene.beams:
                beam.Process()
            for enemy in Shooting.scene.enemies:
                enemy.Process()
            for bullet in Shooting.scene.bullets:
                bullet.Process()
            for explosion in Shooting.scene.explosions:
                explosion.Process()
            for star in Shooting.scene.stars:
                star.Process()
            if Shooting.scene.floatstring != None:
                Shooting.scene.floatstring = Shooting.scene.floatstring.Process()
            if Shooting.scene.gameoverstring != None:
                Shooting.scene.gameoverstring = Shooting.scene.gameoverstring.Process()
            if Shooting.scene.ending != None:
                Shooting.scene.ending = Shooting.scene.ending.Process()
            for i in range(Shooting.scene.status.IncrementEventCount()):
                event_parser.Process()
            if self.gen.__next__() == True:
                state = Shooting.STATE_EXIT_GAMEOVER
            Shooting.scene.CheckBeamEnemyCollision()
            Shooting.scene.CheckBulletPlayerCollision()
            Shooting.scene.CheckEnemyPlayerCollision()
            Shooting.scene.status.IncrementLapTime()
            agent = Gss.agents[Gss.agent_index]
            if Shooting.scene.player.x > FIXED_WIDTH // 2:
                agent.SetCurrentReward(agent.GetCurrentReward() * 0.1)
            if Shooting.scene.player.x < FIXED_WIDTH // 4:
                agent.SetCurrentReward(agent.GetCurrentReward() * 1.1)
            agent.Remember((Gss.joystick.GetStateValues(), Gss.joystick.GetActionValue(), agent.GetCurrentReward()))
            agent.ClearCurrentRewards()
            if not Gss.settings.GetFrameSkipping() or frame_count == 0:
                for star in Shooting.scene.stars:
                    star.Draw(Gss.screen_surface)
                for beam in Shooting.scene.beams:
                    beam.Draw(Gss.screen_surface)
                for enemy in Shooting.scene.enemies:
                    enemy.Draw(Gss.screen_surface)
                Shooting.scene.player.Draw(Gss.screen_surface)
                for explosion in Shooting.scene.explosions:
                    explosion.Draw(Gss.screen_surface)
                for bullet in Shooting.scene.bullets:
                    bullet.Draw(Gss.screen_surface)
                if Shooting.scene.floatstring != None:
                    Shooting.scene.floatstring.Draw(Gss.screen_surface)
                if Shooting.scene.gameoverstring != None:
                    Shooting.scene.gameoverstring.Draw(Gss.screen_surface)
                if Shooting.scene.ending != None:
                    Shooting.scene.ending.Draw(Gss.screen_surface)
                Shooting.scene.status.IncrementFrameNum()
                Shooting.scene.status.Draw(Gss.screen_surface)
                pygame.display.flip()
                ticks = pygame.time.get_ticks() - begin_ticks
                frame_time = 16
                if Gss.settings.GetNoWait():
                    frame_time = 1
                if ticks < frame_time:
                    pygame.time.delay(frame_time - ticks)
            frame_count += 1
            frame_count %= 600
        if not Gss.settings.GetSilent():
            pygame.mixer.music.stop()
        lap_time = Shooting.scene.status.GetLapTime()
        if Shooting.scene.status.GetCompleted() == True and lap_time < Gss.best_lap_time:
            Gss.best_lap_time = lap_time
        return state

    def Move(self):
        while Shooting.scene.gameoverstring == None:
            yield False
        while Shooting.scene.gameoverstring.GetState() == GameOverString.STATE_APPEAR:
            yield False
        count = 0
        while Shooting.scene.gameoverstring.GetState() == GameOverString.STATE_APPEARED:
            trigger = Gss.joystick.GetTrigger()
            if trigger & Joystick.A:
                Shooting.scene.gameoverstring.ToDisappear()
            count += 1
            if count >= 60:
                Shooting.scene.gameoverstring.ToDisappear()
            yield False
        while Shooting.scene.gameoverstring.GetState() == GameOverString.STATE_DISAPPEAR:
            yield False
        while True:
            yield True


if __name__ == "__main__":
    agents = None
    generation = 0
    settings = Settings()
    for argument in enumerate(sys.argv):
        if argument[0] > 0:
            if argument[1][0] == "-":
                for character in argument[1][1:]:
                    if character == "n":
                        settings.SetNoWait(True)
                    elif character == "s":
                        settings.SetSilent(True)
                    elif character == "f":
                        settings.SetFrameSkipping(True)
                    elif character == "e":
                        settings.SetEliteSkipping(True)
            else:
                agents, generation = Agent.Load(argument[1])
    Gss(agents, generation, settings).Main()
