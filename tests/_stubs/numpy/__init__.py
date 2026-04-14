"""Stub numpy for tests."""


class _Array(list):
    def astype(self, dtype=None):
        return self


def concatenate(arrays):
    # Flatten nested lists into single list
    flat = []
    for a in arrays:
        if isinstance(a, (list, tuple)):
            flat.extend(list(a))
        else:
            flat.append(a)
    return _Array(flat)
