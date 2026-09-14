from busroutes.ordering import order_stops, path_cost


def line_matrix(n: int) -> list[list[int]]:
    """Points 0..n-1 on a line, 1 unit apart."""
    return [[abs(i - j) for j in range(n)] for i in range(n)]


def test_path_cost_sums_legs():
    m = line_matrix(5)
    assert path_cost([0, 2, 4], m) == 4


def test_orders_line_from_far_end_towards_school():
    # index 0 = start (school), 5 = school (end), stops are 1..4 scattered on a line
    m = line_matrix(6)
    order = order_stops(stop_indices=[3, 1, 4, 2], start=0, end=5, matrix=m)
    # from the school (0) the cheapest tour visiting all and ending at 5 is monotone
    assert order == [1, 2, 3, 4]


def test_two_opt_untangles_crossing():
    # square: 0=(0,0) start/end school, stops 1=(0,10), 2=(10,10), 3=(10,0)
    coords = [(0, 0), (0, 10), (10, 10), (10, 0)]
    m = [[round(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5) for b in coords] for a in coords]
    order = order_stops(stop_indices=[1, 3, 2], start=0, end=0, matrix=m)
    assert order in ([1, 2, 3], [3, 2, 1])


def test_single_stop():
    m = line_matrix(3)
    assert order_stops(stop_indices=[1], start=0, end=2, matrix=m) == [1]
