import pygame
import math
import numpy as np

# --- Configuration & Metrics ---
WIDTH, HEIGHT = 1000, 1000
FPS = 24

# Physics Constants (Real Earth Data)
G = 6.67430e-11
M_EARTH = 5.972e24       # kg
R_EARTH = 6371.0 * 1000  # meters
MU = G * M_EARTH         # Standard Gravitational Parameter

# Visual Scaling
INITIAL_SCALE = 5000.0   # 1px = 5km
MIN_SCALE = 500.0        # Zoom In Limit
MAX_SCALE = 500000.0     # Zoom Out Limit

# Colors
COLOR_BG = (10, 10, 15)
COLOR_GRID = (30, 30, 40)
COLOR_AXIS = (50, 50, 60)
COLOR_PLANET = (0, 100, 200)
COLOR_ATMOS = (100, 200, 255, 50)
COLOR_SAT = (255, 50, 50)
COLOR_PREDICT = (0, 255, 0)
COLOR_TEXT = (200, 200, 200)
COLOR_VAL = (255, 255, 255)
COLOR_MARKER = (255, 255, 0)
COLOR_CRASH = (255, 100, 0)
TERM_TEXT = (0, 255, 0)

# settin up the cam 
class Camera:
    def __init__(self):
        self.offset_x = 0
        self.offset_y = 0
        self.scale = INITIAL_SCALE
        self.dragging = False
        self.last_mouse = (0, 0)
# cam control
    def to_screen(self, x, y):
        sx = (WIDTH // 2) + (x / self.scale) + self.offset_x
        sy = (HEIGHT // 2) - (y / self.scale) + self.offset_y
        return int(sx), int(sy)

    def handle_input(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                self.dragging = True
                self.last_mouse = event.pos
            elif event.button == 4: # Zoom In
                self.scale = max(MIN_SCALE, self.scale * 0.9)
            elif event.button == 5: # Zoom Out
                self.scale = min(MAX_SCALE, self.scale * 1.1)
        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1: self.dragging = False
        elif event.type == pygame.MOUSEMOTION:
            if self.dragging:
                dx, dy = event.pos[0] - self.last_mouse[0], event.pos[1] - self.last_mouse[1]
                self.offset_x += dx
                self.offset_y += dy
                self.last_mouse = event.pos

# background grid resizing on scrolls
    def draw_grid(self, surface):
        view_w, view_h = WIDTH * self.scale, HEIGHT * self.scale
        raw_step = view_w / 8
        exponent = math.floor(math.log10(raw_step))
        grid_step_m = 10 ** exponent
        if view_w / grid_step_m < 5: grid_step_m /= 2
        
        center_x_phys = -self.offset_x * self.scale
        center_y_phys = self.offset_y * self.scale
        
        left_m, right_m = center_x_phys - (view_w / 2), center_x_phys + (view_w / 2)
        bottom_m, top_m = center_y_phys - (view_h / 2), center_y_phys + (view_h / 2)

        start_x = (math.floor(left_m / grid_step_m)) * grid_step_m
        start_y = (math.floor(bottom_m / grid_step_m)) * grid_step_m

        x = start_x
        while x < right_m:
            sx, _ = self.to_screen(x, 0)
            col = COLOR_AXIS if abs(x) < grid_step_m/10 else COLOR_GRID
            pygame.draw.line(surface, col, (sx, 0), (sx, HEIGHT), 1)
            x += grid_step_m

        y = start_y
        while y < top_m:
            _, sy = self.to_screen(0, y)
            col = COLOR_AXIS if abs(y) < grid_step_m/10 else COLOR_GRID
            pygame.draw.line(surface, col, (0, sy), (WIDTH, sy), 1)
            y += grid_step_m

# --- Physics Classes ---
class Body:
    def __init__(self, r, v, mass, radius_m, color, is_planet=False, name=None):
        self.r = np.array(r, dtype='float64') #position[r]
        self.v = np.array(v, dtype='float64') #velocity[v]
        self.mass = mass #mass[m]
        self.radius_m = radius_m
        self.color = color
        self.is_planet = is_planet
        self.name = name
        self.trail = []
        self.crashed = False

# calculate the acceleration, update [r] and [v]
    def update(self, force, dt):
        if self.crashed: return
        a = force / self.mass
        self.v += a * dt
        self.r += self.v * dt
        
        # 1. Spacing: Only add point if we moved 100km (reduces clutter)
        dist_threshold = 100000 if not self.is_planet else 1e9
        
        if len(self.trail) == 0 or np.linalg.norm(self.trail[-1] - self.r) > dist_threshold:
            self.trail.append(self.r.copy())
            
            # 2. Length Limit: Keep only last 150 points ("Comet Tail")
            if len(self.trail) > 150: 
                self.trail.pop(0)

    def draw(self, surface, camera, font=None):
        # Draw Trail
        if len(self.trail) > 1 and not self.is_planet:
            pts = [camera.to_screen(p[0], p[1]) for p in self.trail]
            # pt 1 trail size
            pygame.draw.lines(surface, self.color, False, pts, 1)
        
        sx, sy = camera.to_screen(self.r[0], self.r[1])
        rad_px = int(self.radius_m / camera.scale)
        if rad_px < 2: rad_px = 2
        
        pygame.draw.circle(surface, self.color, (sx, sy), rad_px)
        if self.is_planet:
            pygame.draw.circle(surface, COLOR_ATMOS, (sx, sy), rad_px + 8, 1)

        # Draw Label
        if self.name and font:
            label = font.render(self.name, True, self.color)
            surface.blit(label, (sx + 12, sy - 12))

# terminal for the visualization
class Terminal:
    def __init__(self):
        self.active = False
        self.input_text = ""
        self.history = ["System Initialized.", "LEO: 'orbit 200 200'", "GTO: 'orbit 200 35786'"]
        self.font = pygame.font.SysFont("consolas", 14)
        
    def log(self, msg):
        self.history.append(msg)
        if len(self.history) > 12: self.history.pop(0)

    def execute(self, cmd_str, sat):
        parts = cmd_str.lower().split()
        if not parts: return
        cmd = parts[0]
        try:
            if cmd == "orbit":
                alt_pe, alt_ap = float(parts[1])*1000, float(parts[2])*1000
                r_pe, r_ap = R_EARTH + alt_pe, R_EARTH + alt_ap
                if r_pe > r_ap: r_pe, r_ap = r_ap, r_pe
                a = (r_pe + r_ap) / 2
                v_pe = math.sqrt(MU * (2/r_pe - 1/a))
                sat.r = np.array([-r_pe, 0.0])
                sat.v = np.array([0.0, -v_pe])
                sat.trail, sat.crashed = [], False 
                self.log(f"Orbit: {alt_pe/1000:.0f}x{alt_ap/1000:.0f} km")
            elif cmd == "burn":
                dv = float(parts[1])
                sat.v += (sat.v / np.linalg.norm(sat.v)) * dv
                self.log(f"Burn: {dv} m/s")
            elif cmd == "reset":
                sat.crashed = True
                self.log("Simulation Halted.")
        except Exception as e: self.log(f"Error: {e}")

    def draw(self, surface):
        if not self.active: return
        s = pygame.Surface((WIDTH, 260))
        s.set_alpha(240); s.fill((10,10,10)); surface.blit(s, (0,0))
        pygame.draw.line(surface, TERM_TEXT, (0, 260), (WIDTH, 260), 2)
        for i, l in enumerate(self.history):
            surface.blit(self.font.render(l, True, TERM_TEXT), (10, 10 + i*20))
        surface.blit(self.font.render("> " + self.input_text + "_", True, (255,255,255)), (10, 230))

# --- Helper Functions ---
def get_gravity(sat, earth):
    dist_vec = earth.r - sat.r
    dist = np.linalg.norm(dist_vec)
    if dist <= (earth.radius_m + sat.radius_m): return None
    return (G * sat.mass * earth.mass / dist**3) * dist_vec

def calculate_orbital_elements(r_vec, v_vec):
    r, v = np.linalg.norm(r_vec), np.linalg.norm(v_vec)
    spec_energy = (v**2)/2 - (MU/r)
    h = np.cross(r_vec, v_vec)
    h_mag = abs(h)
    term = (2 * spec_energy * (h_mag**2)) / (MU**2)
    eccentricity = math.sqrt(max(0, 1 + term))
    return spec_energy, h_mag, eccentricity

def predict_orbit(sat, earth, steps=4000):
    path, cr, cv = [], sat.r.copy(), sat.v.copy()
    min_d, max_d, pe, ap, crash = float('inf'), 0, None, None, False
    
    for _ in range(steps):
        dist = np.linalg.norm(earth.r - cr)
        if dist <= R_EARTH: crash = True; break
        
        acc = (G * M_EARTH / dist**3) * (earth.r - cr)
        dt_pred = 10.0 if dist < R_EARTH * 2 else 50.0 
        cv += acc * dt_pred
        cr += cv * dt_pred
        path.append(cr.copy())
        
        if dist < min_d: min_d, pe = dist, cr.copy()
        if dist > max_d: max_d, ap = dist, cr.copy()
        
    if len(path) > 0 and np.linalg.norm(earth.r - path[-1]) >= max_d: ap = None
    return path, pe, ap, crash

# --- Main Setup ---
pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("2 Body Problem Test")
clock = pygame.time.Clock()
font = pygame.font.SysFont("monospace", 14)
font_bold = pygame.font.SysFont("monospace", 14, bold=True)
label_font = pygame.font.SysFont("monospace", 16, bold=True)

cam = Camera()
term = Terminal()
earth = Body([0,0], [0,0], M_EARTH, R_EARTH, COLOR_PLANET, True)

# Initialize test SAT
sat = Body([-(R_EARTH+400000), 0], [0, -math.sqrt(MU/(R_EARTH+400000))], 500, 10, COLOR_SAT, name="SAT1")

running, paused = True, True

while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT: running = False
        cam.handle_input(event)
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_TAB: term.active = not term.active; paused = True
            elif term.active:
                if event.key == pygame.K_RETURN: term.execute(term.input_text, sat); term.input_text = ""
                elif event.key == pygame.K_BACKSPACE: term.input_text = term.input_text[:-1]
                else: term.input_text += event.unicode
            else:
                if event.key == pygame.K_SPACE: paused = not paused
                if event.key == pygame.K_r: 
                    sat.r = np.array([-(R_EARTH+200000), 0.0])
                    sat.v = np.array([0.0, -math.sqrt(MU/(R_EARTH+200000))])
                    sat.trail = [] # Clear trail on manual reset

    if not paused and not sat.crashed and not term.active:
        for _ in range(10):
            f = get_gravity(sat, earth)
            if f is None: sat.crashed = True; sat.v[:] = 0; break
            sat.update(f, 0.5)

    screen.fill(COLOR_BG)
    cam.draw_grid(screen)
    
    # 1. Draw trajectory
    if not sat.crashed:
        path, pe, ap, crash = predict_orbit(sat, earth)
        if len(path) > 1:
            pts = [cam.to_screen(p[0], p[1]) for p in path]
            pygame.draw.lines(screen, COLOR_CRASH if crash else COLOR_PREDICT, False, pts, 1)
        
        if pe is not None:
            sx, sy = cam.to_screen(pe[0], pe[1])
            pygame.draw.circle(screen, COLOR_MARKER, (sx, sy), 4)
            screen.blit(label_font.render("Pe", True, COLOR_MARKER), (sx + 8, sy - 8))

        if ap is not None:
            sx, sy = cam.to_screen(ap[0], ap[1])
            pygame.draw.circle(screen, COLOR_MARKER, (sx, sy), 4)
            screen.blit(label_font.render("Ap", True, COLOR_MARKER), (sx + 8, sy - 8))

    # 2. Draw Bodies (Foreground)
    earth.draw(screen, cam)
    sat.draw(screen, cam, label_font)
    
    term.draw(screen)

    # --- Telemetry UI ---
    r_mag = np.linalg.norm(sat.r)
    alt = (r_mag - R_EARTH) / 1000.0
    vel = np.linalg.norm(sat.v)
    spec_en, ang_mom, ecc = calculate_orbital_elements(sat.r, sat.v)
    
    period_str = "Escape"
    if spec_en < 0:
        sma = -MU / (2 * spec_en)
        T = 2 * np.pi * math.sqrt(sma**3 / MU)
        m, s = divmod(T, 60); h, m = divmod(m, 60)
        period_str = f"{int(h)}h {int(m)}m"

    ui_data = [
        ("ALTITUDE",  f"{alt:,.1f} km"),
        ("VELOCITY",  f"{vel/1000:.3f} km/s"),
        ("PERIOD",    period_str),
        ("ECCENTRICITY (e)", f"{ecc:.4f}"),
        ("ANG. MOMENTUM (h)", f"{ang_mom/1e9:.2f} G m^2/s"),
        ("SPEC. ENERGY (E)",  f"{spec_en/1e6:.2f} MJ/kg"),
    ]

    box_x, box_y = 10, HEIGHT - 160
    box_w, box_h = 320, 150
    
    pygame.draw.rect(screen, (20, 20, 25), (box_x, box_y, box_w, box_h))
    pygame.draw.rect(screen, (100, 100, 100), (box_x, box_y, box_w, box_h), 1)
    
    for i, (label, val) in enumerate(ui_data):
        y = box_y + 10 + i * 22
        screen.blit(font_bold.render(label, True, COLOR_TEXT), (box_x + 10, y))
        screen.blit(font.render(val, True, COLOR_VAL), (box_x + 190, y))

    pygame.display.flip()
    clock.tick(FPS)

pygame.quit()