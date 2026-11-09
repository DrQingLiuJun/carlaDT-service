"""Forward-only routing on CARLA lane links, with curvature-checked C2 geometry."""

from bisect import bisect_left, bisect_right
import heapq
import itertools
import math


def _lane(wp):
    return wp.road_id, wp.section_id, wp.lane_id


def _point(wp):
    location = wp.transform.location
    return complex(location.x, location.y)


def _direction(yaw):
    yaw = math.radians(yaw)
    return complex(math.cos(yaw), math.sin(yaw))


class NoLaneRoute(ValueError):
    pass


def _forward_route(start, goal, step=0.75, blocked=frozenset()):
    """Use only OpenDRIVE successors. Adjacent and opposing lanes are never jumps."""
    target = _point(goal)
    serial = itertools.count()

    def key(wp):
        return (*_lane(wp), round(wp.s / 0.25))

    start_key = key(start)
    parents = {start_key: (start, None)}
    costs = {start_key: 0.0}
    queue = [(abs(target - _point(start)), next(serial), 0.0, start_key)]
    while queue:
        _, _, cost, current = heapq.heappop(queue)
        if cost != costs[current]:
            continue
        wp, _ = parents[current]
        point = _point(wp)
        gap = target - point
        if (_lane(wp) == _lane(goal) and abs(gap) <= step + 0.05
                and (gap * _direction(wp.transform.rotation.yaw).conjugate()).real >= -0.02):
            route = [goal]
            while current is not None:
                wp, current = parents[current]
                route.append(wp)
            return route[::-1]
        for child in wp.next(step):
            if (_lane(wp), _lane(child)) in blocked:
                continue
            child_key = key(child)
            position = _point(child)
            # A sample may step across a section boundary and past a goal near
            # its beginning. Test the traversed directed edge, not only nodes.
            edge = position - point
            if _lane(child) == _lane(goal) and abs(edge) > 1e-8:
                along = (gap * edge.conjugate()).real / abs(edge)**2
                lateral = abs((gap * edge.conjugate()).imag) / abs(edge)
                if (0 <= along <= 1 and lateral <= .06
                        and (edge * _direction(goal.transform.rotation.yaw).conjugate()).real > 0):
                    route = [goal]
                    while current is not None:
                        parent, current = parents[current]
                        route.append(parent)
                    return route[::-1]
            new_cost = cost + step
            if new_cost >= costs.get(child_key, math.inf):
                continue
            costs[child_key] = new_cost
            parents[child_key] = child, current
            heapq.heappush(queue, (new_cost + abs(target - position),
                                   next(serial), new_cost, child_key))
    raise NoLaneRoute('按车道行驶方向无法连接起终点，请调整选点')


def _quintic(a, b, va, vb, aa, ab, length, t):
    """Position and its first two derivatives in the normalized parameter."""
    c0, c1, c2 = a, va * length, aa * length**2 / 2
    dp = b - c0 - c1 - c2
    dv = vb * length - c1 - 2 * c2
    da = ab * length**2 - 2 * c2
    c3, c4, c5 = 10*dp - 4*dv + da/2, -15*dp + 7*dv - da, 6*dp - 3*dv + da/2
    return (c0 + t*(c1 + t*(c2 + t*(c3 + t*(c4 + t*c5)))),
            c1 + t*(2*c2 + t*(3*c3 + t*(4*c4 + t*5*c5))),
            2*c2 + t*(6*c3 + t*(12*c4 + t*20*c5)))


def plan(start_wp, goal_wp, start, goal, wheelbase, max_steer, width=0.0):
    """Return (x, y, yaw in degrees, curvature in 1/m, source waypoint)."""
    for wp, (x, y, yaw) in ((start_wp, start), (goal_wp, goal)):
        if wp is None or abs(complex(x, y) - _point(wp)) > wp.lane_width / 2:
            raise ValueError('起终点必须在可行驶车道内')
        if (_direction(yaw) * _direction(wp.transform.rotation.yaw).conjugate()).real < math.cos(math.radians(35)):
            raise ValueError('起终点航向与所在车道行驶方向不一致')
    options = start, goal, wheelbase, max_steer, width
    pending = [frozenset()]
    seen = set()
    routes = set()
    first_error = None
    while pending and len(seen) < 48 and len(routes) < 5:
        blocked = pending.pop(0)
        if blocked in seen:
            continue
        seen.add(blocked)
        try:
            route = _forward_route(start_wp, goal_wp, blocked=blocked)
        except NoLaneRoute:
            if first_error is None:
                raise
            continue
        lanes = tuple(lane for lane, _ in itertools.groupby(_lane(wp) for wp in route))
        if lanes in routes:
            continue
        routes.add(lanes)
        try:
            return _smooth_route(route, *options)
        except ValueError as error:
            if first_error is None:
                first_error = error
        adjusted = _widen_turns(route, options)
        if adjusted is not None:
            return adjusted
        pending.extend(blocked | {edge} for edge in zip(lanes, lanes[1:]))
    raise first_error


def _smooth_route(route, start, goal, wheelbase, max_steer, width, spacing=1.4, offset=0.0, widening=0.0, chord_weight=0.0, tangent_scale=1.0, second_scale=1.0, adjustments=None, score=False):
    centers = [_point(wp) for wp in route]
    lengths = [0.] + list(itertools.accumulate(abs(b-a) for a, b in zip(centers, centers[1:])))
    if lengths[-1] < 0.3:
        raise ValueError('起终点距离过短，请选择前方目标')
    # Retain lane geometry in the interior and allow gradual lateral alignment
    # at the two selected poses. Avoid tiny knots at a lane-section boundary.
    indices = [0]
    end_buffer = min(5.0, lengths[-1] / 3)
    for index in range(1, len(route) - 1):
        if (lengths[index] >= end_buffer and lengths[-1] - lengths[index] >= end_buffer
                and lengths[index] - lengths[indices[-1]] >= spacing):
            indices.append(index)
    indices.append(len(route) - 1)
    points = [centers[i] for i in indices]
    points[0], points[-1] = complex(*start[:2]), complex(*goal[:2])
    headings = [start[2]] + [route[i].transform.rotation.yaw for i in indices[1:-1]] + [goal[2]]
    tangents = [_direction(yaw) for yaw in headings]
    stations = [lengths[i] for i in indices]
    adjustments = adjustments or {}
    for j, i in enumerate(indices[1:-1], 1):
        clearance = max(0.0, (route[i].lane_width-width)/2 - 0.06)
        rotation = tangents[j+1] * tangents[j-1].conjugate()
        rate = math.atan2(rotation.imag, rotation.real) / (stations[j+1]-stations[j-1])
        shift = offset - widening * math.tanh(rate / 0.12) + adjustments.get(j, (0., 0.))[0]
        points[j] += 1j*tangents[j] * max(-clearance, min(clearance, shift))
    for j in range(1, len(indices)-1):
        if chord_weight:
            chord = points[j+1] - points[j-1]
            direction = (1-chord_weight)*tangents[j] + chord_weight*chord/abs(chord)
            tangents[j] = direction/abs(direction)
        tangents[j] *= _direction(adjustments.get(j, (0., 0.))[1])
    second = []
    for i, tangent in enumerate(tangents):
        before, after = max(0, i-1), min(len(tangents)-1, i+1)
        rotation = tangents[after] * tangents[before].conjugate()
        heading_rate = math.atan2(rotation.imag, rotation.real) / (stations[after] - stations[before])
        second.append(1j * tangent * heading_rate * second_scale)
    second[0] = second[-1] = 0j
    tangents[1:-1] = [tangent_scale*t for t in tangents[1:-1]]
    limit = math.tan(math.radians(max_steer)) / wheelbase
    result = []
    violations = {}
    for i, (left, right) in enumerate(zip(stations, stations[1:])):
        length = right - left
        count = math.ceil(length / 0.10)
        for j in range(count + 1):
            if i and not j:
                continue
            t = j / count
            point, tangent, accel = _quintic(points[i], points[i+1], tangents[i], tangents[i+1],
                                              second[i], second[i+1], length, t)
            norm = abs(tangent)
            if norm < 1e-6:
                raise ValueError('轨迹存在停顿或折返')
            kappa = (tangent.conjugate() * accel).imag / norm**3
            station = stations[i] + t * length
            nearby = range(bisect_left(lengths, station - 2), bisect_right(lengths, station + 2))
            n = min(nearby, key=lambda k: abs(point - centers[k]))
            wp = route[n]
            forward = _direction(wp.transform.rotation.yaw)
            lateral = abs(((point - centers[n]) * forward.conjugate()).imag)
            if lateral + width / 2 > wp.lane_width / 2 + 0.02 or (tangent * forward.conjugate()).real <= 0:
                raise ValueError('平滑轨迹越出选定车道或逆向，请调整起终点')
            excess = abs(kappa) - limit
            if excess > 1e-5:
                if not score:
                    raise ValueError('道路或选点要求的转弯半径小于车辆允许值，请调整起终点')
                violations[i] = max(excess, violations.get(i, 0.0))
            result.append((point.real, point.imag, math.degrees(math.atan2(tangent.imag, tangent.real)),
                           kappa, wp))
    return (result, violations, len(indices)) if score else result


def _widen_turns(route, options):
    """Search bounded, local knot adjustments while preserving the lane and end poses."""
    profiles = ((2.42, .08, .065, .21, 1.045, 1.31),
                (2.8, .1, .2, 0., 1., 1.),
                (3.65, .135, .125, .025, 1.02, 1.07),
                (1.4, 0., .2, .15, 1., 1.))

    def objective(violations):
        return sum(excess**2 for excess in violations.values())

    for profile in profiles:
        def evaluate(changes):
            try:
                return _smooth_route(route, *options, *profile, adjustments=changes, score=True)
            except ValueError:
                return None

        changes = {}
        value = evaluate(changes)
        if value is None:
            continue
        for step in (.18, .10, .05, .025):
            for _ in range(8):
                path, violations, knots = value
                if not violations:
                    return path
                best = objective(violations)
                candidate = None
                near_turns = {j for i in violations for j in (i-1, i, i+1, i+2) if 0 < j < knots-1}
                for j in sorted(near_turns):
                    offset, yaw = changes.get(j, (0., 0.))
                    for dx, dyaw in ((step, 0.), (-step, 0.), (0., 18*step), (0., -18*step)):
                        if abs(yaw+dyaw) > 12:
                            continue
                        trial = changes.copy()
                        trial[j] = offset+dx, yaw+dyaw
                        result = evaluate(trial)
                        if result is not None and objective(result[1]) < best:
                            best = objective(result[1])
                            candidate = trial, result
                if candidate is None:
                    break
                changes, value = candidate
        if not value[1]:
            return value[0]
    return None

class _SurveyedReverseWaypoint:
    """Geometry of a HAUT lane whose painted direction opposes its XODR heading.

    This adapter is used only by the surveyed eastern return corridor. It does
    not permit reverse traversal on arbitrary roads or change CARLA actors.
    """
    def __init__(self, waypoint):
        self.waypoint = waypoint

    def __getattr__(self, name):
        return getattr(self.waypoint, name)

    @property
    def transform(self):
        from types import SimpleNamespace
        t = self.waypoint.transform
        return SimpleNamespace(location=t.location,
                               rotation=SimpleNamespace(yaw=t.rotation.yaw + 180))

    def next(self, distance):
        allowed = {(43, -3), (253, -2), (10, -3), (24, -3),
                   (55, -2), (22, -3), (17, 3)}
        return [type(self)(wp) for wp in self.waypoint.previous(distance)
                if (wp.road_id, wp.lane_id) in allowed]


def _haut_eastbound_return(road_map, locate_driving, start_wp, goal_wp,
                           start, goal, wheelbase, max_steer, width, vehicle_length):
    """Upper eastbound -> eastern curve -> lower westbound -> native return.

    The repaired corridor follows the arrows visible in the HAUT road surface.
    XODR incorrectly labels its upper eastbound continuation as westbound. Limit
    the correction to this surveyed movement, and retain curvature/width checks.
    """
    if (start_wp.road_id, start_wp.lane_id) != (3, 1):
        raise NoLaneRoute('起点不在已标定的东向归位入口')
    entry = road_map.get_waypoint_xodr(3, 1, 0.)
    first = road_map.get_waypoint_xodr(43, -3, 2.1)
    last = road_map.get_waypoint_xodr(17, 3, 9.)
    exit_wp = road_map.get_waypoint_xodr(188, -1, 0.)
    if any(wp is None for wp in (entry, first, last, exit_wp)):
        raise NoLaneRoute('HAUT 东侧归位回路与当前地图版本不匹配')
    first, last = _SurveyedReverseWaypoint(first), _SurveyedReverseWaypoint(last)

    def pose(wp):
        p = _point(wp)
        return p.real, p.imag, wp.transform.rotation.yaw

    # Verify the surveyed seams still meet; never bridge arbitrary map gaps.
    if abs(_point(entry)-_point(first)) > .25 or abs(_point(last)-_point(exit_wp)) > .25:
        raise NoLaneRoute('HAUT 东侧归位回路的连接坐标已变化')
    approach = plan(start_wp, entry, start, pose(entry), wheelbase, max_steer, width)
    route = [entry] + _forward_route(first, last)
    turn = _smooth_route(route, pose(entry), pose(last), wheelbase, max_steer, width)
    for x, y, yaw, _, _ in turn:
        heading = _direction(yaw)
        for dx in (-vehicle_length/2, 0., vehicle_length/2):
            for dy in (-width/2, width/2):
                p = complex(x, y) + heading * complex(dx, dy)
                if locate_driving(p.real, p.imag) is None:
                    raise ValueError('东侧归位回路的车身空间不足')
    finish = plan(exit_wp, goal_wp, pose(last), goal, wheelbase, max_steer, width)
    return approach + turn[1:] + finish[1:]


def plan_on_map(road_map, locate_driving, start_wp, goal_wp, start, goal,
                wheelbase, max_steer, width, vehicle_length):
    """Use the directed network first, then the mapped HAUT eastern turnaround."""
    try:
        return plan(start_wp, goal_wp, start, goal, wheelbase, max_steer, width)
    except NoLaneRoute:
        if road_map.name.rsplit('/', 1)[-1] != 'HAUT_Map':
            raise
        if (start_wp.road_id, start_wp.lane_id) == (3, 1):
            return _haut_eastbound_return(road_map, locate_driving, start_wp, goal_wp,
                                         start, goal, wheelbase, max_steer, width, vehicle_length)

    # Surveyed movement for this OpenDRIVE layout. Road 10 has a broken
    # same-direction divider; 203 to 188 is the unlinked westbound exit.
    anchors = [road_map.get_waypoint_xodr(*location) for location in
               ((24, -4, 7.0), (10, -3, 8.08), (203, -1, 16.202), (188, -1, 9.266))]
    if any(wp is None for wp in anchors):
        raise NoLaneRoute('右侧环路的车道连接与 HAUT_Map 配置不匹配')
    entry, inner, turn, exit_wp = anchors

    def pose(wp, offset=0j):
        point = _point(wp) + offset
        return point.real, point.imag, wp.transform.rotation.yaw

    def maneuver(first, last, center_lanes, footprint_lanes, lane_change=False,
                 offsets=(0j, 0j), tangent_scales=(1.0, 1.0), outward=0j):
        a, b = _point(first) + offsets[0], _point(last) + offsets[1]
        length = abs(b-a)
        limit = math.tan(math.radians(max_steer)) / wheelbase
        steps = math.ceil(length / 0.08)
        result = []
        previous = first
        for i in range(steps + 1):
            t = i / steps
            point, tangent, accel = _quintic(
                a, b, _direction(first.transform.rotation.yaw) * tangent_scales[0],
                _direction(last.transform.rotation.yaw) * tangent_scales[1],
                0j, 0j, length, t)
            # The outward correction vanishes with its derivatives at both joins.
            u, slope = t * (1-t), 1-2*t
            point += 64 * outward * u**3
            tangent += 192 * outward * u*u * slope
            accel += 384 * outward * u * (slope*slope-u)
            norm = abs(tangent)
            if norm < 1e-6:
                raise ValueError('右侧环路连接存在折返')
            curvature = (tangent.conjugate() * accel).imag / norm**3
            wp = locate_driving(point.real, point.imag)
            if (wp is None or (wp.road_id, wp.lane_id) not in center_lanes
                    or (tangent * _direction(wp.transform.rotation.yaw).conjugate()).real <= 0):
                raise ValueError('右侧环路连接超出允许的顺向车道')
            if lane_change and wp.lane_id != previous.lane_id:
                marking = previous.left_lane_marking
                adjacent = previous.get_left_lane()
                if (marking is None or str(marking.type).split('.')[-1] != 'Broken'
                        or str(previous.lane_change).split('.')[-1] not in ('Left', 'Both')
                        or adjacent is None or _lane(adjacent) != _lane(wp)):
                    raise ValueError('右侧环路变道位置不允许跨越车道线')
            previous = wp
            for x in (-vehicle_length/2, 0., vehicle_length/2):
                for y in (-width/2, width/2):
                    corner = point + tangent/norm * complex(x, y)
                    lane = locate_driving(corner.real, corner.imag)
                    if lane is None or (lane.road_id, lane.lane_id) not in footprint_lanes:
                        raise ValueError('右侧环路车身横向空间不足')
            if abs(curvature) > limit + 1e-5:
                raise ValueError('右侧环路连接的转弯半径小于车辆允许值')
            result.append((point.real, point.imag, math.degrees(math.atan2(tangent.imag, tangent.real)),
                           curvature, wp))
        return result

    def leg(first, last, a, b):
        return plan(first, last, a, b, wheelbase, max_steer, width)

    approach = leg(start_wp, entry, start, pose(entry))
    change_lanes = {(24, -4), (10, -4), (10, -3)}
    change = maneuver(entry, inner, change_lanes, change_lanes | {(203, -1), (253, -2)}, True)
    turn_offset, exit_offset = 0.211, 0.239j
    loop = leg(inner, turn, pose(inner), pose(turn, turn_offset))
    exit_lanes = {(203, -1), (188, -1)}
    merge = maneuver(turn, exit_wp, exit_lanes, exit_lanes,
                     offsets=(turn_offset, exit_offset), tangent_scales=(1.587, 0.954),
                     outward=0.008+0.122j)
    finish = leg(exit_wp, goal_wp, pose(exit_wp, exit_offset), goal)
    return approach + change[1:] + loop[1:] + merge[1:] + finish[1:]
