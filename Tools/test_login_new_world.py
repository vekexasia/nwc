from login_new_world import button


def word(text, left=0, top=0, width=80, height=30):
    return dict(text=text, left=str(left), top=str(top), width=str(width), height=str(height))


assert button([]) is None
assert button([word(t) for t in "PRESS ANY BUTTON TO CONTINUE".split()]) == (960, 880)
selection = [word("SELECT"), word(""), word("CHARACTER")]
assert button(selection + [word("PLAY", 1620, 920)]) == (1660, 935)
assert button(selection + [word("PLAY", 100, 100)]) is None
assert button([word("PLAY", 1620, 920)]) is None
assert button([word("CORINTH"), word("QUESTS")]) is None
print("Login screen checks passed")
