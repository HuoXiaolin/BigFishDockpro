"""Shared colour stops for the desktop spectrum and the capsule halo."""

SPECTRUM_STYLES = (
    ('线条', 'line'), ('柱形', 'bars'), ('圆环', 'ring'), ('镜像', 'mirror'), ('点阵', 'dots'),
    ('立体彩环', 'crown'), ('渐变彩柱', 'peak_bars'), ('彩色粒子球', 'particle_sphere'),
)

SPECTRUM_PALETTES = {
    'colorful': ('经典炫彩', ('#4cdddf', '#639ffb', '#aa83fd', '#f38eba', '#ffd086')),
    'aurora': ('薄荷极光', ('#96f4ad', '#38dabb', '#31b8ce', '#829dff', '#c996ff')),
    'sunset': ('熔金落日', ('#ffdf77', '#ffac4c', '#ff704f', '#ee477e', '#a64692')),
    'ocean': ('深海电光', ('#656af5', '#357ee8', '#189ed2', '#36dce4', '#bbf9ff')),
    'orchid': ('樱莓霓虹', ('#9062ef', '#c74ade', '#f553b9', '#ff86a4', '#ffbcac')),
    'forest': ('森林琥珀', ('#26ad84', '#63c567', '#adc94c', '#e3c750', '#ffac58')),
}
SPECTRUM_COLOR_MODES = tuple((title, key) for key, (title, _) in SPECTRUM_PALETTES.items()) + (('自定义单色', 'mono'),)
