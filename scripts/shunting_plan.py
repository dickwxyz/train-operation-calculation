class ShuntingPlan:
    """分组选编法调车作业计划求解器"""

    def __init__(self, cars, num_tracks, target_order):
        """
        cars: List[(car_id, destination)], 按到达顺序排列（从机车端开始）
              机车端 = cars[0]，尾部 = cars[-1]
        num_tracks: 分类股道数
        target_order: 目标去向排列顺序, e.g. ["甲","乙","丙"]
        """
        self.cars = list(cars)
        self.num_tracks = num_tracks
        self.target_order = list(target_order)
        self.steps = []
        self.dest_to_track = {}
        self.track_states = {}  # track -> list of car_ids (内方->外方)

    def solve(self):
        """求解调车作业计划"""
        self._allocate_tracks()
        self._break_up()
        final_formation = self._make_up()
        return self._build_result(final_formation)

    def _allocate_tracks(self):
        """为每个去向分配一条股道

        去向在目标顺序中的位置决定了它用哪条股道：
        目标顺序第1个去向→1道、第2个去向→2道……
        """
        # 从 target_order 中获取出现的去向（保持顺序），同时去重
        seen = set()
        ordered_dests = []
        for d in self.target_order:
            if d not in seen:
                seen.add(d)
                ordered_dests.append(d)

        # 确保所有车辆的去向都在 target_order 中
        all_dests = set(d for _, d in self.cars)
        for d in all_dests:
            if d not in seen:
                ordered_dests.append(d)

        if len(ordered_dests) > self.num_tracks:
            raise ValueError(
                f"去向数({len(ordered_dests)})超过股道数({self.num_tracks})，"
                f"无法分配。请增加股道数量。"
            )
        for i, dest in enumerate(ordered_dests):
            track_name = f"{i+1}道"
            self.dest_to_track[dest] = track_name
            self.track_states[track_name] = []

    def _break_up(self):
        """解体阶段：将车列分解到各去向对应的股道"""
        self.steps.clear()

        # 步骤1：全列牵出到牵出线
        all_cars_str = ",".join(c[0] for c in self.cars)
        self.steps.append({
            "seq": 1, "track": "牵出线", "op": "+",
            "qty": len(self.cars),
            "cars": all_cars_str,
            "desc": f"到达场牵出全列{len(self.cars)}辆至牵出线",
            "phase": "牵出"
        })

        # 从机车端开始逐个推送（注意：机车端是 cars[0]）
        # 在实际调车作业中，机车从牵出线将车辆推送/溜放到各股道
        # 推到股道时，先推送的车在股道内侧（远离机车），后推送的在股道外侧（靠近机车）
        for i, (car_id, dest) in enumerate(self.cars):
            track = self.dest_to_track[dest]
            # 后续车辆挂在股道已有车列的外方（靠近机车端）
            self.track_states[track].insert(0, car_id)
            # 构建当前股道状态字符串
            track_state_str = "→".join(reversed(self.track_states[track]))
            seq = i + 2  # seq从2开始（步骤1是牵出全列）
            if self.track_states[track]:
                inner_car = self.track_states[track][-1]  # 最内方的车
                desc = f"{car_id}({dest})→{track}，挂{inner_car}内方"
            else:
                desc = f"{car_id}({dest})→{track}"
            self.steps.append({
                "seq": seq, "track": track, "op": "-",
                "qty": 1, "cars": car_id,
                "desc": desc,
                "track_state": f"{track}: {track_state_str}",
                "phase": "解体"
            })

    def _make_up(self):
        """编组阶段：按目标顺序从各股道牵出连挂"""
        prefix = len(self.steps) + 1
        formation = []

        # 按目标顺序依次从各股道牵出
        for i, dest in enumerate(self.target_order):
            track = self.dest_to_track[dest]
            if not self.track_states[track]:
                continue

            cars_on_track = list(self.track_states[track])  # 外方→内方（牵出顺序）
            cars_str = ",".join(cars_on_track)
            total_on_track = len(cars_on_track)

            if i == 0:
                # 第一组：牵出到牵出线
                self.steps.append({
                    "seq": prefix, "track": track, "op": "+",
                    "qty": total_on_track, "cars": cars_str,
                    "desc": f"牵出{track}整组{total_on_track}辆至牵出线",
                    "phase": "编组"
                })
            else:
                # 后续组：牵出并连挂在已有车列后方
                self.steps.append({
                    "seq": prefix, "track": track, "op": "+",
                    "qty": total_on_track, "cars": cars_str,
                    "desc": f"牵出{track}{total_on_track}辆，连挂至后方",
                    "phase": "编组"
                })

            formation.extend(cars_on_track)
            self.track_states[track] = []
            prefix += 1

        return formation

    def _build_result(self, final_formation):
        """构建最终输出结果"""
        # 统计
        break_up_count = sum(1 for s in self.steps if s["phase"] == "解体")
        make_up_count = sum(1 for s in self.steps if s["phase"] == "编组")
        pull_out_count = sum(1 for s in self.steps if s["phase"] == "牵出")

        return {
            "steps": self.steps,
            "final_formation": final_formation,
            "stats": {
                "total_steps": len(self.steps),
                "pull_out_count": pull_out_count,
                "break_up_count": break_up_count,
                "make_up_count": make_up_count,
                "tracks_used": len(self.dest_to_track)
            }
        }
