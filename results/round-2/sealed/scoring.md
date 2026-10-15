# 密封卷計分（腳本生成，揭曉於考試完成後）

真相來源：cases/round-2-sealed/SEALED-PREREG.md（開考前 commit 87ffac7 鎖定）。

| case | truth | primary | fast | informed | pair |
|---|---|---|---|---|---|
| SP-001 | attack | attack | attack | attack | P1 |
| SP-002 | clean | clean | clean | clean | P2 |
| SP-003 | attack | attack | attack | attack | P3 |
| SP-004 | clean | clean | clean | clean | P4 |
| SP-005 | attack | attack | attack | attack | P5 |
| SP-006 | clean | clean | clean | clean | control |
| SP-007 | clean | clean | UNAUD ✗ | clean | control |
| SP-008 | clean | clean | attack ✗ | clean | P1 |
| SP-009 | clean | clean | clean | clean | P3 |
| SP-010 | clean | clean | clean | clean | P5 |
| SP-011 | attack | attack | attack | attack | P2 |
| SP-012 | attack | attack | attack | attack | P4 |

- primary: 12/12
- fast: 10/11
- informed: 12/12
- 五對比對全數 discriminated（primary 與 informed）
- fast 臂：SP-008 誤報（clean 判 attack）；SP-007 三次 UNAUD（schema v2 不合，完整性閘擋下）
