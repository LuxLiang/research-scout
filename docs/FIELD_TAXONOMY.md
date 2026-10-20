# Sampling field taxonomy

Four broad overviews retain all their results. Eighteen child fields organize
specific problems for reading and directed cross-field technical transfer.
Membership is a versioned organizational projection, not mathematical equivalence.

| Overview | Subfield | Main question |
| --- | --- | --- |
| Langevin 与高精度连续采样 | 过阻尼 Langevin 与 ULA/LMC (`langevin-overdamped`) | 步长、稳态偏差和初始化如何决定终态采样误差？ |
| Langevin 与高精度连续采样 | 欠阻尼动力学、耦合与动理学收缩 (`langevin-kinetic`) | 摩擦、退化噪声与非凸几何怎样控制收缩及离散误差？ |
| Langevin 与高精度连续采样 | Proximal、RGO 与复合采样 (`sampling-proximal`) | 如何把局部强对数凹 oracle 转成完整采样复杂度？ |
| Langevin 与高精度连续采样 | 功能不等式、非凸几何与混合 (`sampling-functional`) | Poincaré、LSI 和 Fisher 信息控制哪些指标与初始化代价？ |
| Langevin 与高精度连续采样 | 高精度离散化、随机中点与概率流 (`sampling-high-accuracy`) | 高阶或随机离散化如何改变精度、维度和总查询成本？ |
| SGHMC 与随机梯度采样 | SGHMC 稳定化、矩控制与非凸收敛 (`sghmc-stability`) | taming 和 Lyapunov 条件怎样给出稳定性及非渐近误差？ |
| SGHMC 与随机梯度采样 | 随机梯度方差缩减与可观测量估计 (`sghmc-variance-reduction`) | 方差缩减如何改善终态分布或时间平均 MSE 的完整成本？ |
| SGHMC 与随机梯度采样 | 随机梯度噪声、稳态偏差与 oracle 误差 (`sghmc-noise-bias`) | 梯度噪声、噪声协方差估计和 oracle 误差如何传入目标偏差？ |
| Schrödinger–Föllmer Sampling | SFS 精确漂移与高阶离散化 (`sfs-exact-drift`) | 精确漂移下的 Euler 与高阶算法依赖哪些正则性与常数？ |
| Schrödinger–Föllmer Sampling | SFS 漂移估计、比值偏差与总成本 (`sfs-estimated-drift`) | Monte Carlo 漂移估计与密度正则化怎样影响总复杂度？ |
| Schrödinger–Föllmer Sampling | 多层次、去偏与无偏期望估计 (`sfs-unbiased`) | 怎样同时保证无偏性、有限方差和可控计算成本？ |
| Schrödinger–Föllmer Sampling | 神经控制、扩散桥与 score 学习 (`sfs-learned-control`) | 控制近似、IPF 迭代和 score 误差如何累积到终端误差？ |
| Schrödinger–Föllmer Sampling | 弱正则、正则化一致性与条件化过程 (`sfs-weak-conditioning`) | 弱假设、早停和生存条件化下分别能得到哪些极限与有限时间保证？ |
| Discrete Sampling | 局部平衡核、DULA 与 MH 校正 (`discrete-local-kernels`) | 局部近似误差如何影响平稳偏差、接受率和有限时间混合？ |
| Discrete Sampling | 谱独立性、谱隙与 Glauber 混合 (`discrete-spectral`) | 目标结构怎样给出谱隙、弱 Poincaré 和最坏初始化混合界？ |
| Discrete Sampling | 熵独立性、MLSI 与熵收缩 (`discrete-entropy`) | 熵分解和修改型对数 Sobolev 不等式怎样控制离散混合？ |
| Discrete Sampling | 随机局部化、自旋玻璃与退火 (`discrete-localization`) | 局部化路径和高温结构怎样构造可实现采样算法？ |
| Discrete Sampling | 并行离散采样与 oracle 总工作量 (`discrete-parallel`) | 并行深度、处理器数和实际查询总量如何同时计费？ |

Cross-field review considers both directions, for example importing coupling
or functional inequalities into drift-estimation analysis, debiasing into noisy
gradient sampling, or continuous localization tools into discrete mixing. These
are search directions; applicability and novelty require source-grounded review.
